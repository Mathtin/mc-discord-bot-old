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

import os
import sys
import traceback
import concurrent.futures
import logging
import config
import importlib
import shlex

import asyncio
import discord

from discord import ChannelType

from dotenv import load_dotenv
load_dotenv()

log = logging.getLogger('mc-discord-bot')

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
    return channel.type == ChannelType.text

def is_dm_message(message):
    return isinstance(message.channel, discord.DMChannel)

__module_cache = {}
def get_module_element(path):
    splited_path = path.split('.')
    module_name = '.'.join(splited_path[:-1])
    object_name = splited_path[-1]
    if module_name not in __module_cache:
        __module_cache[module_name] = importlib.import_module(module_name)
    module = __module_cache[module_name]
    return getattr(module, object_name)

def cmd(func):
    if not asyncio.iscoroutinefunction(func):
        raise TypeError(f'{func.__name__}: event registered must be a coroutine function')

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

class InvalidConfigException(Exception):

    def __init__(self, msg, var_name):
        super().__init__(f'{msg}, check {var_name} value in .env file')


class DiscordBot(discord.Client):

    def __init__(self):
        super().__init__()

        self.alias = config.BOT_NAME
        config.botlog.DiscordBotLogHandler.connect_client(self)
        self.token = os.getenv('DISCORD_TOKEN')
        self.guild_id = int(os.getenv('DISCORD_GUILD'))

        # Values initiated on_ready
        self.guild = None
        self.error_channel = None
        self.log_channel = None
        self.control_channel = None
        self.sinks = {}
        self.sinks_by_name = {}
        self.commands = {}

    def run(self):
        super().run(self.token)

    def send_log(self, msg: str):
        if self.log_channel is not None:
            asyncio.create_task(self.log_channel.send(msg))

    def send_error(self, msg: str):
        if self.error_channel is not None:
            asyncio.create_task(self.error_channel.send(msg))

    ######################
    # Additional methods #
    ######################

    def get_attached_sinks(self, id: int):
        if id in self.sinks:
            return self.sinks[id]
        return None

    def get_attached_sink(self, name: str):
        if name in self.sinks_by_name:
            return self.sinks_by_name[name]
        return None

    def add_sink(self, sink: dict, id: int):
        if id in self.sinks:
            self.sinks[id] = self.sinks[id] + [sink]
        else:
            self.sinks[id] = [sink]
        self.sinks_by_name[sink['name']] = sink

    #########
    # Hooks #
    #########

    async def on_error(self, event, *args, **kwargs):
        ex_type = sys.exc_info()[0]

        logging.exception(f'Error on event: {event}')

        exception_lines = traceback.format_exception(*sys.exc_info())

        exception_msg = '`' + ''.join(exception_lines).replace('`', '\'') + '`'

        if self.error_channel is not None and (self.log_channel is None or self.error_channel != self.log_channel):
            await self.error_channel.send(exception_msg)

        if ex_type is InvalidConfigException:
            await self.logout()

    async def on_ready(self):
        # Find guild
        self.guild = self.get_guild(self.guild_id)
        if self.guild is None:
            raise InvalidConfigException("Discord server id is invalid", "DISCORD_GUILD")
        log.info(f'{self.user} is connected to the following guild: {self.guild.name}(id: {self.guild.id})')

        # Resolve channels
        for channel_name in config.channels:
            channel_num = config.channels[channel_name]
            channel_id = get_channel_id(channel_num)
            if channel_id is None:
                raise InvalidConfigException(f'Channel {channel_name}({channel_num}) id is absent', get_channel_env_var_name(channel_num))
            channel = self.get_channel(channel_id)
            if channel is None:
                raise InvalidConfigException(f'Channel {channel_name}({channel_num}) id is invalid', get_channel_env_var_name(channel_num))
            if not is_text_channel(channel):
                raise InvalidConfigException(f"{channel.name}(id: {channel.id}, alias: {channel_name}, num: {channel_num}) is not text channel", get_channel_env_var_name("ERROR"))
            sink = {
                "num": channel_num,
                "name": channel_name,
                "channel": channel
            }
            self.add_sink(sink, channel_id)
            if channel_name == 'log':
                self.log_channel = channel
            if channel_name == 'error':
                self.error_channel = channel
            if channel_name == 'control':
                self.control_channel = channel
                sink["on_message"] = DiscordBot.on_control_message
            if channel_name in config.hooks["message"]:
                hook = get_module_element(config.hooks["message"][channel_name])
                if not asyncio.iscoroutinefunction(hook):
                    raise TypeError(f'{hook.__name__}: event registered must be a coroutine function')
                sink["on_message"] = hook

            log.info(f'Attached to {channel.name} as {channel_name} channel (id: {channel.id}, num:{channel_num})')

        # Attach control hooks
        if self.control_channel is not None and "control" in config.hooks:
            control_hooks = config.hooks["control"]
            for cmd in control_hooks:
                hook = get_module_element(control_hooks[cmd])
                self.commands[cmd] = hook
        
        if 'init' in config.hooks:
            hook = get_module_element(config.hooks['init'])
            if not asyncio.iscoroutinefunction(hook):
                raise TypeError(f'{hook.__name__}: event registered must be a coroutine function')
            await hook(self)

    async def on_message(self, message: discord.Message):
        # ingore own messages
        if message.author == self.user:
            return

        # ingore any foreign messages
        if is_dm_message(message) or message.guild.id != self.guild.id:
            return

        sinks = self.get_attached_sinks(message.channel.id)

        if sinks is None:
            return

        for sink in sinks:
            if "on_message" not in sink:
                continue
            await sink["on_message"](self, message)

    async def on_control_message(self, message: discord.Message):
        argv = shlex.split(message.content)
        ctrl_prefx_len = len(config.CONTROL_PREFIX)
        if len(argv) == 0 or argv[0][: ctrl_prefx_len] != config.CONTROL_PREFIX:
            return

        cmd_name = argv[0][ctrl_prefx_len:]
        if cmd_name == "":
            return
        if cmd_name not in self.commands:
            await message.channel.send("Unknown command")
            return
        
        await self.commands[cmd_name](self, message, argv)
