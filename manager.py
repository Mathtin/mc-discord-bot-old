#!/usr/bin/env python3
# -*- coding: utf-8 -*-
###################################################
#........../\./\...___......|\.|..../...\.........#
#........./..|..\/\.|.|_|._.|.\|....|.c.|.........#
#......../....../--\|.|.|.|i|..|....\.../.........#
#        Mathtin (c)                              #
###################################################
#   Author: Daniel [Mathtin] Shiko                #
#   Copyright (c) 2020 <wdaniil@mail.ru>          #
#   This file is released under the MIT license.  #
###################################################

__author__ = 'Mathtin'

import logging
import json
import asyncio
import os
import requests

import discord
import bot
import config
from util import *
from mcuuid import GetPlayerData
from pydactyl import PterodactylClient
from db import DatabaseContext

from dotenv import load_dotenv
load_dotenv()

log = logging.getLogger('manager-hooks')

#####################
# Message Templates #
#####################

PROFILE_EXAMPLE = """IGN: MyCoolMinecraftNickname
Age: 18
Country: USA
Playstyle & mods you like: building with oak planks
Random info: I'm not even exisiting! I'm just example! Don't blame me please"""

INVALID_PROFILE_DM_MSG = """Hi {0}, you left your profile on ECc server but unfortunately it doesn\'t match specified pattern :(

Please, follow this example:
""" + quote_msg(PROFILE_EXAMPLE) + """

The profile has been removed but don't worry. Here is copy of your message:
{1}
"""

INVALID_PROFILE_IGN_DM_MSG = """Hi {0}, you left your profile on ECc server but unfortunately you specified invalid IGN :(
Please, check your IGN.

The profile has been removed but don't worry. Here is copy of your message:
{1}
"""

FOREIGN_PROFILE_DM_MSG = """Hi {0}, you left your profile on ECc server but unfortunately you mentioned someone else's ign :(

If you believe it isn't your mistake (someone took your ign), please contact anyone on ECc server with this roles: """ + ', '.join(config.roles["admin"]) + """.

The profile has been removed but don't worry. Here is copy of your message:
{1}
"""

#####################
# Module db context #
#####################

class DB:
    dynamic = DatabaseContext('dynamic')
    persist = DatabaseContext('persist')
    ranks = DatabaseContext('ranks')

    @staticmethod
    def save():
        DB.persist.save()
        DB.ranks.save()

    @staticmethod
    def load():
        DB.persist.load()
        DB.ranks.load()

    @staticmethod
    def remove_dynamic(msg_id):
        for table in DB.dynamic:
            if msg_id in table.msg_id:
                res = table.msg_id[msg_id][0]
                table.remove(res)
                return res
        return None

    @staticmethod
    def find_dynamic_whitelisted(ign):
        if ign in DB.dynamic.valid.ign:
            return DB.dynamic.valid.ign[ign][0]
        elif config_path("manager.profile.deprecated.whitelist", False):
            if ign in DB.dynamic.deprecated.ign:
                return DB.dynamic.deprecated.ign[ign][0]
        return None

    @staticmethod
    def remove_all_by_user(user: discord.User):
        res = []
        for table in DB.dynamic:
            for profile in table:
                it_user = profile['msg'].author
                if user.id == it_user.id:
                    res.append(profile)
                    table.remove(profile)
        return res


ptero = PterodactylClient('http://' + os.environ.get("PTERODACTYL_DOMAIN"), os.environ.get("PTERODACTYL_TOKEN"))

##########################
# Profile utility funcs  #
##########################

def parse_dynamic_profile(profile_msg: discord.Message):
    profile = parse_colon_seperated(profile_msg.content)
    to_filter = config_path("manager.profile.format.filter", [])
    for key in to_filter:
        del profile[key]
    profile["msg"] = profile_msg
    profile["msg_id"] = profile_msg.id
    if 'ign' in profile:
        profile["player"] = GetPlayerData(profile["ign"])
    return profile

REQUIRED_DYNAMIC_PROFILE_ENTRIES = ['ign', 'msg', 'msg_id', 'player']
def is_full_profile(profile: dict):
    if profile is None:
        return False
    required = config_path("manager.profile.format.require", []) + REQUIRED_DYNAMIC_PROFILE_ENTRIES
    if not has_keys(profile, required):
        return False
    for key in required:
        if profile[key] == "":
            return False
    return True

def make_persist_profile(message: discord.Message, ign: str):
    player = GetPlayerData(ign)
    if not player.valid:
        return None
    return {
        'ign': ign,
        'author': message.author.id,
        'uuid': str(player.uuid)
    }

def get_missing_entries(profile: dict):
    required = config_path("manager.profile.format.require", []) + ['ign']
    required = list(set(required))
    required = [e for e in required if e not in profile]
    return required

def dynamic_profile_to_whitelist_row(row):
    player = row['player']
    return {
        'uuid' : str(player.uuid),
        'name' : player.username
    }

def persist_profile_to_whitelist_row(row):
    return {
        'uuid' : row['uuid'],
        'name' : row['ign']
    }

def dumps_dynamic_profile(row: dict, pretty=False):
    keys = [k for k in row if k not in ['msg', 'player']]
    obj = {}
    for k in keys:
        obj[k] = row[k]
    if 'msg' in row:
        obj['user'] = row['msg'].author.name
    if 'player' in row and row['player'].valid:
        obj['ign'] = row['player'].username
        obj['uuid'] = str(row['player'].uuid)
    if pretty:
        return json.dumps(obj, indent=4, sort_keys=True)
    return json.dumps(obj)

def dumps_presist_profile(row: dict, pretty=False):
    if pretty:
        return json.dumps(row, indent=4, sort_keys=True)
    return json.dumps(row)

#####################
# Whitelist Methods #
#####################

def build_whitelist_json():
    ign_set = set()
    whitelist = []

    def collect_whitelist(table, converter):
        for profile in table:
            if profile['ign'] in ign_set:
                continue
            wl_row = converter(profile)
            whitelist.append(wl_row)
            ign_set.add(profile['ign'])

    # Add valid
    collect_whitelist(DB.dynamic.valid, dynamic_profile_to_whitelist_row)

    # Add deprecated
    if config_path("manager.profile.deprecated.whitelist", False):
        collect_whitelist(DB.dynamic.deprecated, dynamic_profile_to_whitelist_row)

    # Add persist
    collect_whitelist(DB.persist.root, persist_profile_to_whitelist_row)
    
    return json.dumps(whitelist)

def sync_whitelist():
    # Dump db and whitelist on disk
    DB.save()
    tmp_file_name = "whitelist.json"
    with open(tmp_file_name, "w") as f:
        f.write(build_whitelist_json())
    
    # Get servers from pterodactyl panel
    servers = ptero.client.list_servers().data['data']

    # Sync each server
    for server in servers:
        srv_id = server['attributes']['identifier']

        if srv_id not in config_path("manager.whitelist.servers", []):
            continue

        # Upload whitelist.json
        if config_path("manager.whitelist.upload", False):
            ptero_sftp_upload(srv_id, tmp_file_name, "/whitelist.json")

        try:
            # Reload whitelist
            if config_path("manager.whitelist.reload", False):
                ptero.client.send_console_command(srv_id, "whitelist reload")
        except requests.exceptions.HTTPError as e:
            log.warn("whitelist reload failed: " + str(e.response.content))
            continue

#####################
# Rank Methods      #
#####################

def sync_ranks():
    # Dump db on disk
    DB.save()

    # Get servers from pterodactyl panel
    servers = ptero.client.list_servers().data['data']

    rank_systems = config_path("manager.rank.servers", [])

    # Sync each server
    for server in servers:
        srv_id = server['attributes']['identifier']

        if srv_id not in rank_systems:
            continue

        rank_system = rank_systems[srv_id]

        if rank_system == "spigot":
            ptero_spigot_rank_sync(srv_id)
        elif rank_system == "ftbutilities":
            ptero_ftbutilities_rank_sync(srv_id)

def build_ftbu_ranks_data():
    entries = {}

    for table in DB.ranks:
        for row in table:
            ign = row['ign']
            if ign in entries:
                entries[ign]['ranks'].append(table.name)
            else:
                entries[ign] = {
                    'ign': row['ign'],
                    'uuid': row['uuid'].replace('-',''),
                    'ranks': [table.name]
                }
    
    entrie_format = '// {ign}\n[{uuid}]\nparent: {ranks}\n'
    entrie_conv = lambda e: {'ign': e['ign'], 'uuid': e['uuid'], 'ranks': ', '.join(e['ranks'])}

    converted_entries = [entrie_conv(entries[ign]) for ign in entries]
    formated_entries = [entrie_format.format(**e) for e in converted_entries]

    return '\n'.join(formated_entries)


def ptero_ftbutilities_rank_sync(srv_id):

    # Dump players.txt
    tmp_file_name = "player_ftbu_ranks.txt"
    with open(tmp_file_name, "w") as f:
        f.write(build_ftbu_ranks_data())
    
    # Upload players.txt
    if config_path("manager.rank.upload", False):
        ptero_sftp_upload(srv_id, tmp_file_name, "/local/ftbutilities/players.txt")

def ptero_spigot_rank_sync(srv_id):
    pass

####################
# Profile Handlers #
####################

async def handle_profile_message(client: bot.DiscordBot, message: discord.Message):
    profile = parse_dynamic_profile(message)

    # Handle invalid profile
    if not is_full_profile(profile):
        if is_admin_message(message):
            log.info(f'Ignoring message from {message.author.name} as admin\'s message: {json.dumps(message.content)}')
        else:
            await handle_invalid_profile(client, message, profile)
        return
    elif not profile['player'].valid:
        await handle_invalid_profile(client, message, profile)
        return

    # Search for profile with same ign
    existing_profile = DB.find_dynamic_whitelisted(profile['ign'])

    # Handle user trying to add profile with duplicate ign
    if existing_profile is not None:
        if is_same_author(existing_profile['msg'], message):
            await handle_profile_update(client, existing_profile, profile)
        else:
            await handle_duplicate_profile_ign(client, existing_profile, profile)
            return
    
    DB.dynamic.valid.add(profile)

async def handle_deprecated_profile_message(client: bot.DiscordBot, message: discord.Message):
    profile = parse_dynamic_profile(message)

    # Handle invalid profile
    if not is_full_profile(profile) or not profile['player'].valid:
        if config_path("manager.profile.invalid.default.delete", False):
            await message.delete()
        else:
            if not is_full_profile(profile):
                required = get_missing_entries(profile)
                required_str = ', '.join([str(s) for s in required])
                profile['error'] = f"deprecated, missing entries: {required_str}"
            else:
                profile['error'] = "deprecated, invalid ign"
            DB.dynamic.invalid.add(profile)
        return

    # Search for profile with same ign
    existing_profile = DB.find_dynamic_whitelisted(profile['ign'])

    # Handle user trying to add profile with duplicate ign
    if existing_profile is not None:
        if is_same_author(existing_profile['msg'], message):
            await handle_profile_update(client, existing_profile, profile)
        else:
            await handle_duplicate_deprecated_profile_ign(client, existing_profile, profile)
            return
    
    DB.dynamic.deprecated.add(profile)

async def handle_invalid_profile(client: bot.DiscordBot, message: discord.Message, profile: dict):
    user = message.author

    # Handle missing entries in profile
    if not is_full_profile(profile):
        log.info(f"Invalid profile by {user.name}: {dumps_dynamic_profile(profile)}")
        if config_path("manager.profile.invalid.default.delete", False):
            await message.delete()
        else:
            required = get_missing_entries(profile)
            required_str = ', '.join([str(s) for s in required])
            profile['error'] = f"missing entries: {required_str}"
            DB.dynamic.invalid.add(profile)
        if config_path("manager.profile.invalid.default.dm", False):
            await user.send(INVALID_PROFILE_DM_MSG.format(user.name, quote_msg(message.content)))
    # Handle invalid ign
    elif not profile['player'].valid:
        log.info(f"Invalid ign by {user.name}: {dumps_dynamic_profile(profile)}")
        if config_path("manager.profile.invalid.ign.delete", False):
            await message.delete()
        else:
            profile['error'] = "invalid ign"
            DB.dynamic.invalid.add(profile)
        if config_path("manager.profile.invalid.ign.dm", False):
            await user.send(INVALID_PROFILE_IGN_DM_MSG.format(user.name, quote_msg(message.content)))
    # Handle unknown profile error
    else:
        raise RuntimeError(f"Something went wrong cheking {user.name}'s profile: {dumps_dynamic_profile(profile)}")

async def handle_profile_update(client: bot.DiscordBot, old_profile: dict, profile: dict):
    log.info(f"{profile['msg'].author.name}'s profile update detected {dumps_dynamic_profile(old_profile)} -> {dumps_dynamic_profile(profile)}")
    DB.remove_dynamic(old_profile['msg_id'])
    if old_profile['msg'].id != profile['msg'].id:
        if config_path("manager.profile.update.old.delete", False):
            await old_profile['msg'].delete()
        else:
            old_profile['error'] = "old profile"
            DB.dynamic.invalid.add(old_profile)

async def handle_duplicate_profile_ign(client: bot.DiscordBot, or_profile: dict, profile: dict):
    message = profile['msg']
    user = message.author
    or_user = or_profile['msg'].author
    log.warn(f"Duplicate ign detected in {user.name}'s profile: {dumps_dynamic_profile(profile)}, original profile from {or_user.name}: {dumps_dynamic_profile(or_profile)}")
    if config_path("manager.profile.invalid.duplicate.delete", False):
        await message.delete()
    else:
        profile['error'] = "duplicate ign"
        DB.dynamic.invalid.add(profile)
    if config_path("manager.profile.invalid.duplicate.dm", False):
        await user.send(FOREIGN_PROFILE_DM_MSG.format(user.name, quote_msg(message.content)))

async def handle_duplicate_deprecated_profile_ign(client: bot.DiscordBot, or_profile: dict, profile: dict):
    message = profile['msg']
    user = message.author
    or_user = or_profile['msg'].author
    log.warn(f"Duplicate ign detected in deprecated {user.name}'s profile: {dumps_dynamic_profile(profile)}, original profile from {or_user.name}: {dumps_dynamic_profile(or_profile)}")
    if config_path("manager.profile.invalid.duplicate.delete", False):
        await message.delete()
    else:
        profile['error'] = "duplicate ign"
        DB.dynamic.invalid.add(profile)

##################
# Event Handlers #
##################

async def init(client: bot.DiscordBot):
    # Lock current async context
    init_lock = asyncio.Lock()
    async with init_lock:
        # Init db
        DB.load()
        DB.dynamic.clear()

        # Make user-member cache
        member_cache = {}

        # Get profile source channel
        profile_channel = client.get_attached_sink("profile")["channel"]
        
        # Iterate over each profile message
        async for message in profile_channel.history(limit=None,oldest_first=True):
            user = message.author

            # Skip own messages
            if user == client.user:
                continue

            # Get user-member object
            if user.id not in member_cache:
                try:
                    member = await client.guild.fetch_member(user.id)
                    if member is None:
                        member = user
                except discord.errors.NotFound:
                    member = user
                member_cache[user.id] = member
            user = member_cache[user.id]
            message.author = user

            # Handle message as deprecated if user left server
            if not is_user_member(user):
                log.info(f'Deprecated {user.name}\'s profile detected: {json.dumps(message.content)}')
                if config_path("manager.profile.deprecated.delete", False):
                    await message.delete()
                else:
                    await handle_deprecated_profile_message(client, message)
                continue
            
            # Handle profile message from member
            await handle_profile_message(client, message)
        
        # Sync whitelist/ranking state
        sync_whitelist()
        sync_ranks()

async def new_profile(client: bot.DiscordBot, message: discord.Message):
    await handle_profile_message(client, message)
    sync_whitelist()

async def edit_profile(client: bot.DiscordBot, msg: discord.Message):
    old_profile = DB.remove_dynamic(msg.id)
    await handle_profile_message(client, msg)
    if old_profile is None:
        log.error("Unknown profile detected! Reloading!")
        await init(client)
        return
    if is_full_profile(old_profile):
        new_profile = DB.find_dynamic_whitelisted(msg.id)
        if new_profile is not None and new_profile['ign'] == old_profile['ign']:
            return
    sync_whitelist()

async def delete_profile(client: bot.DiscordBot, msg_id: int):
    DB.remove_dynamic(msg_id)
    sync_whitelist()

async def user_left(client: bot.DiscordBot, member: discord.Member):
    log.warn(f"User {member.name} left server, moving profiles")
    deleted_profiles = DB.remove_all_by_user(member)
    if config_path("manager.profile.deprecated.delete", False):
        for profile in deleted_profiles:
            await profile['msg'].delete()
    else:
        for profile in deleted_profiles:
            await handle_deprecated_profile_message(client, profile['msg'])

############################
# Control command Handlers #
############################

@cmdcoro
async def ping(client: bot.DiscordBot, mgs_obj: discord.Message):
    await mgs_obj.channel.send("pong")

@cmdcoro
async def show_db(client: bot.DiscordBot, mgs_obj: discord.Message, name: str):
    # Gather table
    if name not in DB.dynamic:
        await mgs_obj.channel.send("No such table")
        return
    table = DB.dynamic[name]

    # Handle empty table
    if table.size() == 0:
        await mgs_obj.channel.send("Table is empty")
        return
    
    # Handle non-empty table
    await mgs_obj.channel.send("##### TABLE START #####")
    for profile in table:
        row_str = '`' + dumps_dynamic_profile(profile, pretty=True).replace('`', '\'') + '`'
        await mgs_obj.channel.send(row_str)
    await mgs_obj.channel.send("##### TABLE END #####")

@cmdcoro
async def show_persist_db(client: bot.DiscordBot, mgs_obj: discord.Message):
    table = DB.persist.root

    # Handle empty table
    if table.size() == 0:
        await mgs_obj.channel.send("Database is empty")
        return

    # Handle non-empty table
    await mgs_obj.channel.send("##### DATABASE START #####")
    for profile in table:
        row_str = '`' + dumps_presist_profile(profile, pretty=True).replace('`', '\'') + '`'
        await mgs_obj.channel.send(row_str)
    await mgs_obj.channel.send("##### DATABASE END #####")

@cmdcoro
async def send_to_sink(client: bot.DiscordBot, mgs_obj: discord.Message, sink_name: str, message: str):
    sink = client.get_attached_sink(sink_name)
    if sink is None:
        await mgs_obj.channel.send(f"Sink {sink_name} not found")
        return
    channel = sink['channel']
    await channel.send(message)
    await mgs_obj.channel.send(f"Message sent to {channel.mention}")

@cmdcoro
async def add_persist_profile(client: bot.DiscordBot, mgs_obj: discord.Message, ign: str):
    table = DB.persist.root

    # Parse profile
    profile = make_persist_profile(mgs_obj, ign)
    if profile is None:
        await mgs_obj.channel.send(f"Invalid ign")
        return
    
    # Handle already existing persist profile
    if ign in table.ign:
        or_profile = table.ign[ign][0]
        await mgs_obj.channel.send(f"This ign is already added by <@{or_profile['author']}>")
        return
    
    # Handle already existing dynamic profile
    existing_profile = DB.find_dynamic_whitelisted(ign)
    if existing_profile is not None:
        or_msg = existing_profile['msg']
        await mgs_obj.channel.send(f"Note: profile with specified ign is exists (by {or_msg.author.mention})")

    table.add(profile)
    sync_whitelist()
    await mgs_obj.channel.send(f"Added successfully")

@cmdcoro
async def remove_persist_profile(client: bot.DiscordBot, mgs_obj: discord.Message, ign: str):
    table = DB.persist.root

    if ign not in table.ign:
        await mgs_obj.channel.send(f"Specified ign not added yet")
        return
    profile = table.ign[ign][0]
    
    # Handle already existing dynamic profile
    existing_profile = DB.find_dynamic_whitelisted(ign)
    if existing_profile is not None:
        or_msg = existing_profile['msg']
        await mgs_obj.channel.send(f"Note: profile with specified ign is exists (by {or_msg.author.mention})")
    
    table.remove(profile)
    sync_whitelist()
    await mgs_obj.channel.send(f"Removed successfully")

@cmdcoro
async def reload(client: bot.DiscordBot, mgs_obj: discord.Message):
    await mgs_obj.channel.send(f"Reloading")
    await init(client)
    await mgs_obj.channel.send(f"Reloaded data successfully")

@cmdcoro
async def sync(client: bot.DiscordBot, mgs_obj: discord.Message):
    await mgs_obj.channel.send(f"Syncing whitelist")
    sync_whitelist()
    await mgs_obj.channel.send(f"Synced successfully")

@cmdcoro
async def get_profile(client: bot.DiscordBot, mgs_obj: discord.Message, name: str):
    convert = lambda p: '`' + dumps_dynamic_profile(p, pretty=True).replace('`', '\'') + '`'

    await mgs_obj.channel.send("##### SEARCH START #####")

    for table in DB.dynamic:
        for profile in table:
            ign = profile['ign']
            user = profile['msg'].author

            if user.name == name or user.name + user.discriminator == name or f'{user.name}#{user.discriminator}' == name:
                row_str = f'Found {user.mention}\'s dynamic profile (same name)\n' + convert(profile)
            elif user.display_name == name:
                row_str = f'Found {user.mention}\'s dynamic profile (same display name)\n' + convert(profile)
            elif ign == name:
                row_str = f'Found {user.mention}\'s dynamic profile (same ign)\n' + convert(profile)
            else:
                continue

            await mgs_obj.channel.send(row_str)

    for profile in DB.persist.root:
        ign = profile['ign']
        user_id = profile['author']

        if ign == name:
            row_str = f'Found <@{user_id}>\'s persist profile\n' + convert(profile)
        else:
            continue

        await mgs_obj.channel.send(row_str)


    await mgs_obj.channel.send("##### SEARCH END #####")

@cmdcoro
async def add_rank(client: bot.DiscordBot, mgs_obj: discord.Message, ign: str, rank: str):
    # Gather table
    if rank not in DB.ranks:
        await mgs_obj.channel.send("No such rank")
        return
    table = DB.ranks[rank]
    
    # Handle already ranked profile
    if ign in table.ign:
        or_profile = table.ign[ign][0]
        await mgs_obj.channel.send(f"This ign is already ranked as {rank} by <@{or_profile['author']}>")
        return

    # Find and convert profile
    profile = DB.find_dynamic_whitelisted(ign)
    if profile is None:
        profile = persist_profile_to_whitelist_row(DB.persist.root.ign[ign][0]) \
                    if ign in DB.persist.root.ign else None
    else:
        profile = dynamic_profile_to_whitelist_row(profile)

    # Handle absent profile
    if profile is None:
        await mgs_obj.channel.send(f"No profile found for specified ign")
        return

    table.add({'ign': ign, 'author': mgs_obj.author.id, 'uuid': profile['uuid']})
    sync_ranks()
    await mgs_obj.channel.send(f"Ranked {ign} as {rank} successfully")

@cmdcoro
async def remove_rank(client: bot.DiscordBot, mgs_obj: discord.Message, ign: str, rank: str):
    # Gather table
    if rank not in DB.ranks:
        await mgs_obj.channel.send("No such rank")
        return
    table = DB.ranks[rank]

    if ign not in table.ign:
        await mgs_obj.channel.send(f"Specified ign not ranked as {rank} yet")
        return
    profile = table.ign[ign][0]
    
    table.remove(profile)
    sync_ranks()
    await mgs_obj.channel.send(f"Removed rank {rank} from {ign} successfully")

@cmdcoro
async def get_rank(client: bot.DiscordBot, mgs_obj: discord.Message, ign: str):
    # Handle absent profile
    if ign not in DB.persist.root.ign and DB.find_dynamic_whitelisted(ign) is None:
        await mgs_obj.channel.send(f"No profile found for specified ign")
        return
    ranks = []
    # Gather ranks
    for table in DB.ranks:
        if ign not in table.ign:
            continue
        ranked_by = table.ign[ign][0]['author']
        ranks.append(f'{table.name} (ranked by <@{ranked_by}>)')
    # Handle no ranks
    if len(ranks) == 0:
        await mgs_obj.channel.send(f"No ranks found for {ign}")
        return
    rank_list = "\n".join(ranks)
    await mgs_obj.channel.send(f"{ign}'s ranks:\n{rank_list}")

@cmdcoro
async def show_ranked_users(client: bot.DiscordBot, mgs_obj: discord.Message, rank: str):
    # Gather table
    if rank not in DB.ranks:
        await mgs_obj.channel.send("No such rank")
        return
    table = DB.ranks[rank]

    # Handle empty table
    if table.size() == 0:
        await mgs_obj.channel.send("Database is empty")
        return

    # Handle non-empty table
    await mgs_obj.channel.send("##### DATABASE START #####")
    for profile in table:
        row_str = '`' + dumps_presist_profile(profile, pretty=True).replace('`', '\'') + '`'
        await mgs_obj.channel.send(row_str)
    await mgs_obj.channel.send("##### DATABASE END #####")

@cmdcoro
async def show_ranks(client: bot.DiscordBot, mgs_obj: discord.Message):
    ranks = ', '.join([r.name for r in DB.ranks])
    await mgs_obj.channel.send(f"Available ranks: {ranks}")
