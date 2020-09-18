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
import re
import json
import asyncio
import uuid
import os
import os.path
import paramiko
from base64 import b64decode

import pysftp
import discord
import bot
import config
from util import *
from mcuuid import GetPlayerData
from pydactyl import PterodactylClient

from dotenv import load_dotenv
load_dotenv()

log = logging.getLogger('manager-hooks')

##########
# Consts #
##########

PTERO_DOMAIN = os.environ.get("PTERODACTYL_DOMAIN")
PTERO_HTTP = 'http://' + PTERO_DOMAIN

#####################
# Profile Templates #
#####################

PROFILE_PATTERN = re.compile(r"^\s*IGN\s*:(.+?)Age\s*:(.+?)Country\s*:(.+?)Playstyle & mods you like\s*:(.+?)Random info\s*:(.+?)$", re.DOTALL + re.IGNORECASE)

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

The profile has been remove but don't worry. Here is copy of your message:
{1}
"""

INVALID_PROFILE_IGN_DM_MSG = """Hi {0}, you left your profile on ECc server but unfortunately you specified invalid IGN :(
Please, check your IGN.

The profile has been remove but don't worry. Here is copy of your message:
{1}
"""

FOREIGN_PROFILE_DM_MSG = """Hi {0}, you left your profile on ECc server but unfortunately you mentioned someone else's ign :(

If you believe it isn't your mistake (someone took your ign), please contact anyone on ECc server with this roles: """ + ', '.join(config.roles["admin"]) + """.

And btw I had to remove it but don't worry. Here is copy of your message:
{1}
"""

##################
# Module globals #
##################

dynamic_db = {
    'valid': {},
    'invalid': {},
    'deprecated': {}
}
persist_db = {}
ptero = PterodactylClient(PTERO_HTTP, os.environ.get("PTERODACTYL_TOKEN"))

##########################
# Profile utility funcs #
##########################

def old_parse_profile(profile_msg: discord.Message):
    m = PROFILE_PATTERN.fullmatch(profile_msg.content)
    if m is None:
        return None
    ign = m.group(1).strip()
    return {
        'ign': ign,
        'age': m.group(2).strip(),
        'country': m.group(3).strip(),
        'playstyle': m.group(4).strip(),
        'info': m.group(5).strip(),
        'msg': profile_msg,
        'player': GetPlayerData(ign)
    }

def parse_dynamic_profile(profile_msg: discord.Message):
    profile = parse_colon_seperated(profile_msg.content)
    to_filter = config_path("manager.profile.format.filter", [])
    for key in to_filter:
        del profile[key]
    profile["msg"] = profile_msg
    if 'ign' in profile:
        profile["player"] = GetPlayerData(profile["ign"])
    return profile

def is_full_profile(profile: dict):
    if profile is None:
        return False
    required = config_path("manager.profile.format.require", []) + ['ign', 'msg', 'player']
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
        'author': message.author.name,
        'uuid': str(player.uuid)
    }

########################
# Whitelist DB Methods #
########################

def find_dynamic_profile(id, categories=dynamic_db.keys()):
    for category in categories:
        if id in dynamic_db[category]:
            return dynamic_db[category][id]
    return None

def is_dynamic_profile_exists(id, categories=dynamic_db.keys()):
    return find_dynamic_profile(id, categories) is not None

def find_whitelisted_dynamic_profile(ign: str):
    if ign in dynamic_db['valid']:
        return dynamic_db['valid'][ign]
    elif config_path("manager.profile.deprecated.whitelist", False):
        if ign in dynamic_db['deprecated']:
            return dynamic_db['deprecated'][ign]
    return None

def add_dynamic_profile(category, profile: dict):
    if profile is None:
        return False
    msg_id = profile['msg'].id
    if msg_id in dynamic_db[category]:
        return False
    if category == 'valid' or category == 'deprecated':
        ign = profile['ign']
        if ign in dynamic_db[category]:
            return False
        dynamic_db[category][ign] = profile
    dynamic_db[category][msg_id] = profile
    return True

def update_dynamic_profile(profile: dict):
    if profile is None:
        return False
    ign = profile['ign']
    msg_id = profile['msg'].id
    for category in dynamic_db:
        if msg_id not in dynamic_db[category]:
            continue
        dynamic_db[category][msg_id] = profile
        if ign in dynamic_db[category]:
            dynamic_db[category][ign] = profile
        return True
    return False

def remove_dynamic_profile(profile: dict):
    if profile is None:
        return False
    ign = profile['ign']
    msg_id = profile['msg'].id
    for category in dynamic_db:
        if msg_id not in dynamic_db[category]:
            continue
        del dynamic_db[category][msg_id]
        if ign in dynamic_db[category]:
            del dynamic_db[category][ign]
        return True
    return False

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

def dynamic_row_to_whitelist_row(row):
    player = row['player']
    return {
        'uuid' : str(player.uuid),
        'name' : player.username
    }

def persist_row_to_whitelist_row(row):
    return {
        'uuid' : row['uuid'],
        'name' : row['ign']
    }

def get_whitelist_json():
    ign_set = set()
    res = []

    # Add valid
    valid_profiles = dynamic_db['valid']
    for id in valid_profiles:
        profile = valid_profiles[id]
        if profile['ign'] in ign_set:
            continue
        wl_row = dynamic_row_to_whitelist_row(profile)
        res.append(wl_row)
        ign_set.add(profile['ign'])

    # Add deprecated
    if config_path("manager.profile.deprecated.whitelist", False):
        deprecated_profiles = dynamic_db['deprecated']
        for id in deprecated_profiles:
            profile = deprecated_profiles[id]
            if profile['ign'] in ign_set:
                continue
            wl_row = dynamic_row_to_whitelist_row(profile)
            res.append(wl_row)
            ign_set.add(profile['ign'])

    # Add persist
    for id in persist_db:
        profile = persist_db[id]
        if profile['ign'] in ign_set:
            continue
        wl_row = persist_row_to_whitelist_row(profile)
        res.append(wl_row)
        ign_set.add(profile['ign'])
    
    return json.dumps(res)

def save_persist_db():
    with open(config.PERSIST_WHITELIST_PATH, "w") as f:
        json.dump(persist_db, f)

def load_persist_db():
    global persist_db
    if os.path.exists(config.PERSIST_WHITELIST_PATH):
        try:
            with open(config.PERSIST_WHITELIST_PATH, "r") as f:
                persist_db = json.load(f)
        except json.decoder.JSONDecodeError:
            log.error("Failed to load persist database, removing invalid data")
            persist_db = {}
            save_persist_db()

def sync_whitelist():
    # Dump persist db and whitelist on disk
    save_persist_db()
    tmp_file_name = "whitelist.json"
    with open(tmp_file_name, "w") as f:
        f.write(get_whitelist_json())
    
    # Get servers from pterodactyl panel
    servers = ptero.client.list_servers().data['data']
    cnopts = pysftp.CnOpts()
    cnopts.hostkeys = None

    # Sync each server
    for server in servers:
        srv_id = server['attributes']['identifier']

        # Upload whitelist.json
        if config_path("manager.whitelist.upload", False):
            username = f'{os.environ.get("PTERODACTYL_USERNAME")}.{srv_id}'
            password = os.environ.get("PTERODACTYL_PASSWORD")
            with pysftp.Connection(PTERO_DOMAIN, username=username, password=password, cnopts=cnopts, port=2022) as sftp:
                sftp.put(tmp_file_name, "/whitelist.json")

        # Reload whitelist
        if config_path("manager.whitelist.reload", False):
            ptero.client.send_console_command(srv_id, "whitelist reload")

####################
# Profile Handlers #
####################

async def handle_profile_message(client: bot.DiscordBot, message: discord.Message):
    profile = parse_dynamic_profile(message)

    if not is_full_profile(profile):
        if is_admin_message(message):
            log.info(f'Ignoring message from {message.author.name} as admin\'s message: {json.dumps(message.content)}')
        else:
            await handle_invalid_profile(client, message, profile)
        return
    
    if not profile['player'].valid:
        await handle_invalid_profile(client, message, profile)
        return

    ign = profile['ign']
    existing_profile = find_whitelisted_dynamic_profile(ign)

    # If user trying to add profile with duplicate ign
    if existing_profile is not None:
        if is_same_author(existing_profile['msg'], message):
            await handle_profile_update(client, existing_profile, profile)
        else:
            await handle_duplicate_profile_ign(client, existing_profile, profile)
    else:
        add_dynamic_profile('valid', profile)

async def handle_deprecated_profile_message(client: bot.DiscordBot, message: discord.Message):
    profile = parse_dynamic_profile(message)

    if not is_full_profile(profile) or not profile['player'].valid:
        if config_path("manager.profile.invalid.default.delete", False):
            await message.delete()
        else:
            if not is_full_profile(profile):
                profile['error'] = "deprecated, missing entries"
            else:
                profile['error'] = "deprecated, invalid ign"
            add_dynamic_profile('invalid', profile)
        return

    ign = profile['ign']
    existing_profile = find_whitelisted_dynamic_profile(ign)

    # If user trying to add profile with duplicate ign
    if existing_profile is not None:
        if is_same_author(existing_profile['msg'], message):
            await handle_profile_update(client, existing_profile, profile)
        else:
            await handle_duplicate_deprecated_profile_ign(client, existing_profile, profile)
    else:
        add_dynamic_profile('deprecated', profile)

async def handle_invalid_profile(client: bot.DiscordBot, message: discord.Message, profile: dict):
    user = message.author

    if not is_full_profile(profile):
        log.info(f"Invalid profile by {user.name}: {dumps_dynamic_profile(profile)}")
        if config_path("manager.profile.invalid.default.delete", False):
            await message.delete()
        else:
            profile['error'] = "missing entries"
            add_dynamic_profile('invalid', profile)
        if config_path("manager.profile.invalid.default.dm", False):
            await user.send(INVALID_PROFILE_DM_MSG.format(user.name, quote_msg(message.content)))
    elif not profile['player'].valid:
        log.info(f"Invalid ign by {user.name}: {dumps_dynamic_profile(profile)}")
        if config_path("manager.profile.invalid.ign.delete", False):
            await message.delete()
        else:
            profile['error'] = "invalid ign"
            add_dynamic_profile('invalid', profile)
        if config_path("manager.profile.invalid.ign.dm", False):
            await user.send(INVALID_PROFILE_IGN_DM_MSG.format(user.name, quote_msg(message.content)))
    else:
        raise RuntimeError(f"Something went wrong cheking {user.name}'s profile: {dumps_dynamic_profile(profile)}")

async def handle_profile_update(client: bot.DiscordBot, old_profile: dict, profile: dict):
    update_dynamic_profile(profile)
    if old_profile['msg'].id != profile['msg'].id:
        log.info(f"{profile['msg'].author.name}'s profile update detected {dumps_dynamic_profile(old_profile)} -> {dumps_dynamic_profile(profile)}")
        if config_path("manager.profile.update.old.delete", False):
            await old_profile['msg'].delete()
        else:
            old_profile['error'] = "old profile"
            add_dynamic_profile('invalid', old_profile)

async def handle_duplicate_profile_ign(client: bot.DiscordBot, or_profile: dict, profile: dict):
    message = profile['msg']
    user = message.author
    or_user = or_profile['msg'].author
    log.warn(f"Duplicate ign detected in {user.name}'s profile: {dumps_dynamic_profile(profile)}, original profile from {or_user.name}: {dumps_dynamic_profile(or_profile)}")
    if config_path("manager.profile.invalid.duplicate.delete", False):
        await message.delete()
    else:
        profile['error'] = "duplicate ign"
        add_dynamic_profile('invalid', profile)
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
        add_dynamic_profile('invalid', profile)

##################
# Event Handlers #
##################

async def init(client: bot.DiscordBot):
    load_persist_db()
    profile_channel = client.get_attached_sink("profile")["channel"]
    init_lock = asyncio.Lock()
    async with init_lock:
        messages_history = await profile_channel.history(limit=None,oldest_first=True).flatten()
        for message in messages_history:
            user = message.author

            if user == client.user:
                continue

            # Filter messages from users not on server
            if not is_user_member(user):
                log.info(f'Deprecated {user.name}\'s profile detected: {json.dumps(message.content)}')
                if config_path("manager.profile.deprecated.delete", False):
                    await message.delete()
                else:
                    await handle_deprecated_profile_message(client, message)
                continue

            await handle_profile_message(client, message)
        sync_whitelist()

async def new_profile(client: bot.DiscordBot, message: discord.Message):
    await handle_profile_message(client, message)
    sync_whitelist()

async def edit_profile(client: bot.DiscordBot, before: discord.Message, after: discord.Message):
    profile = find_dynamic_profile(before.id)
    remove_dynamic_profile(profile)
    await handle_profile_message(client, after)
    sync_whitelist()

async def delete_profile(client: bot.DiscordBot, message: discord.Message):
    profile = find_dynamic_profile(message.id)
    remove_dynamic_profile(profile)
    sync_whitelist()

async def user_left(client: bot.DiscordBot, member: discord.Member):
    log.warn(f"User {member.name} left server, reloading data")
    await init(client)

############################
# Control command Handlers #
############################

@cmdcoro
async def ping(client: bot.DiscordBot, mgs_obj: discord.Message):
    await mgs_obj.channel.send("pong")

@cmdcoro
async def show_db(client: bot.DiscordBot, mgs_obj: discord.Message, name: str):
    if name not in dynamic_db:
        await mgs_obj.channel.send("No such database")
        return
    db = dynamic_db[name]
    if not db:
        await mgs_obj.channel.send("Database is empty")
        return
    await mgs_obj.channel.send("##### DATABASE START #####")
    for id in db:
        profile = db[id]
        if 'ign' in profile and profile['ign'] == id:
            continue
        row_str = '`' + dumps_dynamic_profile(profile, pretty=True).replace('`', '\'') + '`'
        await mgs_obj.channel.send(row_str)
    await mgs_obj.channel.send("##### DATABASE END #####")

@cmdcoro
async def show_persist_db(client: bot.DiscordBot, mgs_obj: discord.Message):
    if not persist_db:
        await mgs_obj.channel.send("Database is empty")
        return
    await mgs_obj.channel.send("##### DATABASE START #####")
    for id in persist_db:
        row_str = '`' + dumps_presist_profile(persist_db[id], pretty=True).replace('`', '\'') + '`'
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
    profile = make_persist_profile(mgs_obj, ign)
    if profile is None:
        await mgs_obj.channel.send(f"Invalid ign")
        return
    if ign in persist_db:
        or_profile = persist_db[ign]
        await mgs_obj.channel.send(f"This ign is already added by {or_profile['author']}")
        return
    existing_profile = find_whitelisted_dynamic_profile(ign)
    if existing_profile is not None:
        or_msg = existing_profile['msg']
        await mgs_obj.channel.send(f"Note: profile with specified ign is exists (by {or_msg.author.mention})")
    persist_db[ign] = profile
    sync_whitelist()
    await mgs_obj.channel.send(f"Added successfully")

@cmdcoro
async def remove_persist_profile(client: bot.DiscordBot, mgs_obj: discord.Message, ign: str):
    if ign not in persist_db:
        await mgs_obj.channel.send(f"Specified ign not added yet")
        return
    existing_profile = find_whitelisted_dynamic_profile(ign)
    if existing_profile is not None:
        or_msg = existing_profile['msg']
        await mgs_obj.channel.send(f"Note: profile with specified ign is exists (by {or_msg.author.mention})")
    del persist_db[ign]
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
