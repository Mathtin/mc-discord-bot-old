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
import importlib
import config
import asyncio
import discord
import pysftp
import shlex
import os

#################
# Utility Funcs #
#################

def has_keys(d: dict, keys: list):
    for key in keys:
        if key not in d:
            return False
    return True

__module_cache = {}
def get_module_element(path: str):
    splited_path = path.split('.')
    module_name = '.'.join(splited_path[:-1])
    object_name = splited_path[-1]
    if module_name not in __module_cache:
        __module_cache[module_name] = importlib.import_module(module_name)
    module = __module_cache[module_name]
    return getattr(module, object_name)

def quote_msg(msg: str):
    return '\n'.join(['> ' + s for s in msg.split('\n')])

def parse_colon_seperated(msg: str):
    lines = [s.strip() for s in msg.split('\n')]
    lines = [s for s in lines if s != ""]
    res = {}
    for s in lines:
        try:
            k = s[: s.index(':')].strip()
            v = s[s.index(':')+1:].strip()
            if k != "":
                res[k.lower()] = v
        except ValueError:
            continue
    return res

def config_path(path: str, default):
    path_slitted = path.split('.')
    if not hasattr(config, path_slitted[0]):
        return default
    node = getattr(config, path_slitted[0])
    for el in path_slitted[1:]:
        if el in node:
            node = node[el]
        else:
            return default
    return node

def parse_control_message(message: discord.Message):
        prefix = config_path("hooks.control.prefix", '!')
        prefix_len = len(prefix)
        msg = message.content.strip()

        msg_prefix = msg[: prefix_len]
        msg_suffix = msg[prefix_len :]

        if msg_prefix != prefix or msg_suffix == "":
            return None

        return shlex.split(msg_suffix)

def check_coroutine(func):
    if not asyncio.iscoroutinefunction(func):
        raise NotCoroutineException(func)

def build_cmdcoro_usage(cmdname, func):
    prefix = config_path("hooks.control.prefix", '!')
    f_args = func.__code__.co_varnames[:func.__code__.co_argcount]
    assert len(f_args) >= 2
    f_args = f_args[2:]
    args_str = ' ' + ' '.join(["{%s}" % arg for arg in f_args])
    return f'{prefix}{cmdname}' + args_str

def cmdcoro(func):
    check_coroutine(func)

    f_args = func.__code__.co_varnames[:func.__code__.co_argcount]
    assert len(f_args) >= 2
    f_args = f_args[2:]

    async def wrapped_func(client, message, argv):
        if len(f_args) != len(argv) - 1:
            usage_str = 'Usage: ' + build_cmdcoro_usage(argv[0], func)
            await message.channel.send(usage_str)
        else:
            await func(client, message, *argv[1:])

    setattr(wrapped_func, "or_cmdcoro", func)
    
    return wrapped_func

def ptero_sftp_upload(srv_id, src_path, dst_path):
    username = f'{os.environ.get("PTERODACTYL_USERNAME")}.{srv_id}'
    password = os.environ.get("PTERODACTYL_PASSWORD")
    domain = os.environ.get("PTERODACTYL_DOMAIN")
    cnopts = pysftp.CnOpts()
    cnopts.hostkeys = None
    with pysftp.Connection(domain, username=username, password=password, cnopts=cnopts, port=2022) as sftp:
        sftp.put(src_path, dst_path)

###################
# Utility Classes #
###################

class InvalidConfigException(Exception):

    def __init__(self, msg: str, var_name: str):
        super().__init__(f'{msg}, check {var_name} value in .env file')

class NotCoroutineException(TypeError):

    def __init__(self, func):
        super().__init__(f'{str(func)} is not a coroutine function')

class DiscordBotLogHandler(logging.Handler):
    
    instances = {}

    @staticmethod
    def connect_client(client):
        if client.alias in DiscordBotLogHandler.instances:
            DiscordBotLogHandler.instances[client.alias].client = client

    def __init__(self, bot):
        super().__init__()
        DiscordBotLogHandler.instances[bot] = self
        self.client = None

    def emit(self, record):
        if self.client is None:
            return

        try:
            msg = '`' + self.format(record).replace('`', '\'') + '`'
            self.client.send_log(msg)
        except RecursionError:
            raise
        except Exception:
            self.handleError(record)

###########################
# Bot model utility funcs #
###########################

def is_admin_message(msg: discord.Message):
    for role in msg.author.roles:
        if role.name in config.roles["admin"]:
            return True
    return False

def is_user_member(user: discord.User):
    return isinstance(user, discord.Member)

def get_channel_env_var_name(n):
    return f'DISCORD_CHANNEL_{n}'

def get_channel_id(n):
    var_name = get_channel_env_var_name(n)
    try:
        res = os.environ.get(var_name)
        return int(res) if res is not None else None
    except ValueError as e:
        raise InvalidConfigException(str(e), var_name)

def is_text_channel(channel):
    return channel.type == discord.ChannelType.text

def is_dm_message(message: discord.Message):
    return isinstance(message.channel, discord.DMChannel)

def is_same_author(m1: discord.Message, m2: discord.Message):
    return m1.author.id == m2.author.id
