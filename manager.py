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
import pickle
from base64 import b64decode

import pysftp
import discord
import bot
import config
from mcuuid import GetPlayerData
from pydactyl import PterodactylClient

from dotenv import load_dotenv
load_dotenv()

log = logging.getLogger('manager-hooks')

PROFILE_PATTERN = re.compile(r"^\s*IGN\s*:(.+?)Age\s*:(.+?)Country\s*:(.+?)Playstyle & mods you like\s*:(.+?)Random info\s*:(.+?)$", re.DOTALL + re.IGNORECASE)

db = {}
persist_db = {}
PTERO_DOMAIN = os.environ.get("PTERODACTYL_DOMAIN")
PTERO_HTTP = 'http://' + PTERO_DOMAIN
ptero = PterodactylClient(PTERO_HTTP, os.environ.get("PTERODACTYL_TOKEN"))

def quote_msg(msg):
    return '\n'.join(['> ' + s for s in msg.split('\n')])

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

def is_admin_message(msg: discord.Message):
    for role in msg.author.roles:
        if role.name in config.roles["admin"]:
            return True
    return False

def is_user_member(user: discord.User):
    return isinstance(user, discord.Member)

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

def persist_profile(message: discord.Message, ign: str):
    player = GetPlayerData(ign)
    if not player.valid:
        return None
    return {
        'ign': ign,
        'author': message.author.name,
        'uuid': str(player.uuid)
    }


##################
# Async Handlers #
##################

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
load_persist_db()

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
        continue
        with pysftp.Connection(PTERO_DOMAIN, username=username, password=password, cnopts=cnopts, port=2022) as sftp:
            sftp.put(tmp_file_name, "/whitelist.json")
        ptero.client.send_console_command(srv_id, "whitelist reload")

async def handle_profile_message(client: bot.DiscordBot, message: discord.Message):
    profile = parse_profile(message)

    if profile is None and is_admin_message(message):
        log.warn(f'Ignoring message from {message.author.name} as admin\'s message: {message.content}')
        return

    if is_invalid_profile(profile):
        await handle_invalid_profile(client, message, profile)
        return

    if profile['ign'] in db and db[profile['ign']]['msg'].author.id == message.author.id:
        await handle_profile_update(client, profile)
        return

    # If user trying to add profile with duplicate ign
    if profile['ign'] in db:
        await handle_duplicate_profile_ign(client, profile)
        return

    await handle_new_profile(client, profile)

    sync_whitelist()

async def handle_invalid_profile(client: bot.DiscordBot, message: discord.Message, profile: dict):
    user = message.author
    #await message.delete()
    if profile is None:
        #await user.send(INVALID_PROFILE_DM_MSG.format(user.name, quote_msg(message.content)))
        #await client.control_channel.send("Invalid profile by {0}:\n{1}".format(user.mention, quote_msg(message.content)))
        await client.control_channel.send("Invalid profile by {0}".format(user.mention))
    elif not profile['player'].valid:
        #await user.send(INVALID_PROFILE_IGN_DM_MSG.format(user.name, quote_msg(message.content)))
        #await client.control_channel.send("Invalid ign by {0}:\n{1}".format(user.mention, quote_msg(message.content)))
        await client.control_channel.send("Invalid ign by {0}".format(user.mention))
    else:
        #await user.send(INVALID_PROFILE_DM_MSG.format(user.name, quote_msg(message.content)))
        #await client.control_channel.send("Invalid profile by {0}:\n{1}".format(user.mention, quote_msg(message.content)))
        await client.control_channel.send("Invalid profile by {0}".format(user.mention))

async def handle_profile_update(client: bot.DiscordBot, profile: dict):
    ign = profile['ign']
    or_message = db[ign]['msg']
    db[ign] = profile
    if or_message.id != profile['msg'].id:
        await client.control_channel.send("Profile update by {0} from:\n{1}\nto:\n{2}".format(or_message.author.mention, quote_msg(or_message.content), quote_msg(profile['msg'].content)))
        #await or_message.delete()

async def handle_duplicate_profile_ign(client: bot.DiscordBot, profile: dict):
    message = profile['msg']
    user = message.author
    or_profile = db[profile['ign']]
    or_user = or_profile['msg'].author
    log.warn(f"Removing {user.name}'s profile. Reason: duplicate ign. Profile: {str(profile)}, original profile from {or_user.name}: {str(or_profile)}")
    #await message.delete()
    #await user.send(FOREIGN_PROFILE_DM_MSG.format(user.name, quote_msg(message.content)))
    await client.control_channel.send(f"Duplicate ign in {user.mention}'s profile. Provided: {quote_msg(message.content)}, original profile from {or_user.mention}: {quote_msg(or_profile['msg'].content)}")

async def handle_new_profile(clien: bot.DiscordBot, profile: discord.Message):
    db[profile['ign']] = profile

##################
# Event Handlers #
##################

async def init(client: bot.DiscordBot):
    profile_channel = client.get_attached_sink("profile")["channel"]
    async for message in profile_channel.history(limit=None,oldest_first=True):
        user = message.author

        if user == client.user:
            continue

        # Filter messages from users not on server
        if not is_user_member(user):
            log.warn(f'Removing {user.name}\'s profile message as he/she left server')
            #await message.delete()
            #await client.control_channel.send("Old profile (user left) by {0}:\n{1}".format(user.name, quote_msg(message.content)))
            continue

        await handle_profile_message(client, message)
    

async def new_profile(client: bot.DiscordBot, message: discord.Message):
    await handle_profile_message(client, message)


############################
# Control command Handlers #
############################

@bot.cmd
async def ping(client: bot.DiscordBot, mgs_obj: discord.Message):
    await mgs_obj.channel.send("pong")

@bot.cmd
async def show_db(client: bot.DiscordBot, mgs_obj: discord.Message):
    if not db:
        await mgs_obj.channel.send("Database is empty")
    for id in db:
        row_str = '`' + db_row_to_str(db[id]).replace('`', '\'') + '`'
        await mgs_obj.channel.send(row_str)

@bot.cmd
async def show_persist_db(client: bot.DiscordBot, mgs_obj: discord.Message):
    if not persist_db:
        await mgs_obj.channel.send("Database is empty")
    for id in persist_db:
        row_str = '`' + persist_db_row_to_str(persist_db[id]).replace('`', '\'') + '`'
        await mgs_obj.channel.send(row_str)

@bot.cmd
async def send_to_sink(client: bot.DiscordBot, mgs_obj: discord.Message, sink_name: str, message: str):
    sink = client.get_attached_sink(sink_name)
    if sink is None:
        await mgs_obj.channel.send(f"Sink {sink_name} not found")
        return
    channel = sink['channel']
    await channel.send(message)
    await mgs_obj.channel.send(f"Message sent to {channel.mention}")

@bot.cmd
async def add_persist_profile(client: bot.DiscordBot, mgs_obj: discord.Message, ign: str):
    profile = persist_profile(mgs_obj, ign)
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

@bot.cmd
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

@bot.cmd
async def reload(client: bot.DiscordBot, mgs_obj: discord.Message):
    await mgs_obj.channel.send(f"Reloading")
    await init(client)
    await mgs_obj.channel.send(f"Reloaded data successfully")
