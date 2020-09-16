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
import tempfile
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

DB_LINE_TEMPLATE = """{{
    "user":      {user}, 
    "ign":       {ign}, 
    "uuid":      {uuid},
    "age":       {age},  
    "country":   {country},
    "playstyle": {playstyle},
    "info":      {info}
}}"""

PERSIST_DB_LINE_TEMPLATE = """{{
    "user":      {user}, 
    "ign":       {ign}, 
    "uuid":      {uuid}
}}"""

#####################
# Message Templates #
#####################

PROFILE_EXAMPLE = """IGN: MyCoolMinecraftNickname
Age: 18
Country: USA
Playstyle & mods you like: building with oak planks
Random info: I'm not even exisiting! I'm just example! Don't blame me please"""

INVALID_PROFILE_DM_MSG = """Hi {0}, you left your profile on ECC server but unfortunately it doesn\'t match specified pattern :(

Please, follow this example:
""" + quote_msg(PROFILE_EXAMPLE) + """

And btw I had to remove it but do not worry. Here is copy of your message:
{1}
"""

INVALID_PROFILE_IGN_DM_MSG = """Hi {0}, you left your profile on ECC server but unfortunately you specified invalid IGN :(
Please, check your IGN.

And btw I had to remove it but do not worry. Here is copy of your message:
{1}
"""

FOREIGN_PROFILE_DM_MSG = """Hi {0}, you left your profile on ECC server but unfortunately you mentioned someone else's ign :(

If you believe it isn't your mistake (someone took your ign), please contact anyone on ECC server with this roles: """ + ', '.join(config.roles["admin"]) + """.

And btw I had to remove it but don't worry. Here is copy of your message:
{1}
"""

##################
# Module globals #
##################

db = {}
persist_db = {}
ptero = PterodactylClient(PTERO_HTTP, os.environ.get("PTERODACTYL_TOKEN"))

##########################
# Profile utility funcs #
##########################

def parse_profile(profile_msg: discord.Message):
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

def is_partially_empty_profile(profile: dict):
    for key in profile:
        if profile[key] == "":
            return True
    return False

def is_invalid_profile(profile: dict):
    return profile is None or is_partially_empty_profile(profile) or not profile['player'].valid

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

def db_row_to_str(row: dict):
    obj = {
        'user': json.dumps(row['msg'].author.display_name),
        'ign': json.dumps(row['player'].username),
        'uuid': json.dumps(str(row['player'].uuid)),
        'age': json.dumps(row['age']),
        'country': json.dumps(row['country']),
        'playstyle': json.dumps(row['playstyle']),
        'info': json.dumps(row['info'])
    }
    return DB_LINE_TEMPLATE.format(**obj)

def persist_db_row_to_str(row: dict):
    obj = {
        'user': json.dumps(row['author']),
        'ign': json.dumps(row['ign']),
        'uuid': json.dumps(row['uuid'])
    }
    return PERSIST_DB_LINE_TEMPLATE.format(**obj)

def get_whitelist_json():
    res = []
    for id in db:
        player = db[id]['player']
        res.append ({
            'uuid' : str(player.uuid),
            'name' : player.username
        })
    for id in persist_db:
        if id in db:
            continue
        player = persist_db[id]
        res.append ({
            'uuid' : player['uuid'],
            'name' : player['ign']
        })
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

#paramiko.common.logging.basicConfig(level=paramiko.common.DEBUG)
def sync_whitelist():
    save_persist_db()
    #tmp_file_name = tempfile.mktemp()
    tmp_file_name = "whitelist.json"
    with open(tmp_file_name, "w") as f:
        f.write(get_whitelist_json())
    servers = ptero.client.list_servers().data['data']
    for server in servers:
        cnopts = pysftp.CnOpts()
        cnopts.hostkeys = None
        srv_id = server['attributes']['identifier']
        username = f'{os.environ.get("PTERODACTYL_USERNAME")}.{srv_id}'
        password = os.environ.get("PTERODACTYL_PASSWORD")
        if config_path("whitelist.upload", False):
            with pysftp.Connection(PTERO_DOMAIN, username=username, password=password, cnopts=cnopts, port=2022) as sftp:
                sftp.put(tmp_file_name, "/whitelist.json")
        if config_path("whitelist.reload", False):
            ptero.client.send_console_command(srv_id, "whitelist reload")

####################
# Profile Handlers #
####################

async def handle_profile_message(client: bot.DiscordBot, message: discord.Message):
    profile = parse_profile(message)

    if is_invalid_profile(profile):
        if is_admin_message(message):
            log.info(f'Ignoring message from {message.author.name} as admin\'s message: {message.content}')
        else:
            await handle_invalid_profile(client, message, profile)
        return

    ign = profile['ign']

    # If user trying to add profile with duplicate ign
    if ign in db:
        if db[ign]['msg'].author.id == message.author.id:
            await handle_profile_update(client, profile)
        else:
            await handle_duplicate_profile_ign(client, profile)
    else:
        await handle_new_profile(client, profile)

    sync_whitelist()

async def handle_deprecated_profile_message(client: bot.DiscordBot, message: discord.Message):
    profile = parse_profile(message)

    if is_invalid_profile(profile):
        if config_path("profile.invalid.default.delete", False):
            await message.delete()
        return

    ign = profile['ign']

    # If user trying to add profile with duplicate ign
    if ign in db:
        if db[ign]['msg'].author.id == message.author.id:
            await handle_profile_update(client, profile)
        else:
            await handle_duplicate_deprecated_profile_ign(client, profile)
    else:
        await handle_new_profile(client, profile)

    sync_whitelist()

async def handle_invalid_profile(client: bot.DiscordBot, message: discord.Message, profile: dict):
    user = message.author
    if profile is None:
        log.info(f"Invalid profile by {user.name}: {json.dumps(message.content)}")
        if config_path("profile.invalid.default.delete", False):
            await message.delete()
        if config_path("profile.invalid.default.dm", False):
            await user.send(INVALID_PROFILE_DM_MSG.format(user.name, quote_msg(message.content)))
    elif not profile['player'].valid:
        log.info(f"Invalid ign by {user.name}: {json.dumps(message.content)}")
        if config_path("profile.invalid.ign.delete", False):
            await message.delete()
        if config_path("profile.invalid.ign.dm", False):
            await user.send(INVALID_PROFILE_IGN_DM_MSG.format(user.name, quote_msg(message.content)))
    else:
        log.info(f"Invalid profile by {user.name}: {json.dumps(message.content)}")
        if config_path("profile.invalid.default.delete", False):
            await message.delete()
        if config_path("profile.invalid.default.dm", False):
            await user.send(INVALID_PROFILE_DM_MSG.format(user.name, quote_msg(message.content)))

async def handle_profile_update(client: bot.DiscordBot, profile: dict):
    ign = profile['ign']
    message = profile['msg']
    or_message = db[ign]['msg']
    db[ign] = profile
    if or_message.id != profile['msg'].id:
        log.info(f"{or_message.author.name}'s profile update detected {json.dumps(or_message.content)} -> {json.dumps(message.content)}")
        if config_path("profile.update.old.delete", False):
            await or_message.delete()

async def handle_duplicate_profile_ign(client: bot.DiscordBot, profile: dict):
    ign = profile['ign']
    message = profile['msg']
    or_message = db[ign]['msg']
    user = message.author
    or_user = or_message.author
    log.warn(f"Duplicate ign detected in {user.name}'s profile: {json.dumps(message.content)}, original profile from {or_user.name}: {json.dumps(or_message.content)}")
    if config_path("profile.invalid.duplicate.delete", False):
        await message.delete()
    if config_path("profile.invalid.duplicate.dm", False):
        await user.send(FOREIGN_PROFILE_DM_MSG.format(user.name, quote_msg(message.content)))

async def handle_duplicate_deprecated_profile_ign(client: bot.DiscordBot, profile: dict):
    ign = profile['ign']
    message = profile['msg']
    or_message = db[ign]['msg']
    user = message.author
    or_user = or_message.author
    log.warn(f"Duplicate ign detected in deprecated {user.name}'s profile: {json.dumps(message.content)}, original profile from {or_user.name}: {json.dumps(or_message.content)}")
    if config_path("profile.invalid.duplicate.delete", False):
        await message.delete()

async def handle_new_profile(clien: bot.DiscordBot, profile: discord.Message):
    db[profile['ign']] = profile

##################
# Event Handlers #
##################

async def init(client: bot.DiscordBot):
    load_persist_db()
    profile_channel = client.get_attached_sink("profile")["channel"]
    async for message in profile_channel.history(limit=None,oldest_first=True):
        user = message.author

        if user == client.user:
            continue

        # Filter messages from users not on server
        if not is_user_member(user):
            log.info(f'Deprecated {user.name}\'s profile detected: {json.dumps(message.content)}')
            if config_path("profile.deprecated.delete", False):
                await message.delete()
            elif config_path("profile.deprecated.whitelist", False):
                await handle_deprecated_profile_message(client, message)
            continue

        await handle_profile_message(client, message)
    

async def new_profile(client: bot.DiscordBot, message: discord.Message):
    await handle_profile_message(client, message)
    

async def edit_profile(client: bot.DiscordBot, before: discord.Message, after: discord.Message):
    await handle_profile_message(client, after)

async def delete_profile(client: bot.DiscordBot, message: discord.Message):
    profile = parse_profile(message)

    if profile is None or is_invalid_profile(profile):
        return

    if profile['ign'] not in db or db[profile['ign']]['msg'].author.id != message.author.id:
        return

    del db[profile['ign']]

    sync_whitelist()

async def user_left(client: bot.DiscordBot, member: discord.Member):
    to_delete = []
    for id in db:
        profile = db[id]
        if profile['msg'].author.id == member.id:
            to_delete.append(id)

    for id in to_delete:
        del db[id]

    sync_whitelist()

############################
# Control command Handlers #
############################

@cmdcoro
async def ping(client: bot.DiscordBot, mgs_obj: discord.Message):
    await mgs_obj.channel.send("pong")

@cmdcoro
async def show_db(client: bot.DiscordBot, mgs_obj: discord.Message):
    if not db:
        await mgs_obj.channel.send("Database is empty")
    for id in db:
        row_str = '`' + db_row_to_str(db[id]).replace('`', '\'') + '`'
        await mgs_obj.channel.send(row_str)

@cmdcoro
async def show_persist_db(client: bot.DiscordBot, mgs_obj: discord.Message):
    if not persist_db:
        await mgs_obj.channel.send("Database is empty")
    for id in persist_db:
        row_str = '`' + persist_db_row_to_str(persist_db[id]).replace('`', '\'') + '`'
        await mgs_obj.channel.send(row_str)

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
    if ign in db:
        or_msg = db[ign]['msg']
        await mgs_obj.channel.send(f"Note: profile with specified ign is exists (by {or_msg.author.mention})")
    persist_db[ign] = profile
    sync_whitelist()
    await mgs_obj.channel.send(f"Added successfully")

@cmdcoro
async def remove_persist_profile(client: bot.DiscordBot, mgs_obj: discord.Message, ign: str):
    if ign not in persist_db:
        await mgs_obj.channel.send(f"Specified ign not added yet")
        return
    if ign in db:
        or_msg = db[ign]['msg']
        await mgs_obj.channel.send(f"Note: profile with specified ign is exists (by {or_msg.author.mention})")
    del persist_db[ign]
    sync_whitelist()
    await mgs_obj.channel.send(f"Removed successfully")

@cmdcoro
async def reload(client: bot.DiscordBot, mgs_obj: discord.Message):
    await mgs_obj.channel.send(f"Reloading")
    await init(client)
    await mgs_obj.channel.send(f"Reloaded data successfully")
