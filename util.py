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
import os

#################
# Utility Funcs #
#################

__module_cache = {}
def get_module_element(path):
    splited_path = path.split('.')
    module_name = '.'.join(splited_path[:-1])
    object_name = splited_path[-1]
    if module_name not in __module_cache:
        __module_cache[module_name] = importlib.import_module(module_name)
    module = __module_cache[module_name]
    return getattr(module, object_name)

def quote_msg(msg):
    return '\n'.join(['> ' + s for s in msg.split('\n')])

def config_path(path, default):
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

def check_coroutine(func):
    if not asyncio.iscoroutinefunction(func):
        raise NotCoroutineException(func)

def cmdcoro(func):
    check_coroutine(func)

    f_args = func.__code__.co_varnames[:func.__code__.co_argcount]
    assert len(f_args) >= 2
    f_args = f_args[2:]

    async def wrapped_func(client, message, argv):
        if len(f_args) != len(argv) - 1:
            args_str = ' ' + ' '.join(["{%s}" % arg for arg in f_args])
            usage_str = f'Usage: {argv[0]}' + args_str
            await message.channel.send(usage_str)
        else:
            await func(client, message, *argv[1:])
    
    return wrapped_func

###################
# Utility Classes #
###################

class InvalidConfigException(Exception):

    def __init__(self, msg, var_name):
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

def is_dm_message(message):
    return isinstance(message.channel, discord.DMChannel)
