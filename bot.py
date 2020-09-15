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

import asyncio
import discord

from discord import ChannelType

log = logging.getLogger('mc-discord-bot')

def get_channel_env_var_name(n):
    return f'DISCORD_CHANNEL_{n}'

def get_channel_id(n):
    res = os.environ.get(get_channel_env_var_name(n))
    return int(res) if res is not None else None

def is_text_channel(channel):
    return channel.type == ChannelType.text

class InvalidConfigException(Exception):

    def __init__(self, msg, var_name):
        super().__init__(f'{msg}, check {var_name} value in .env file')


class DiscordBot(discord.Client):

    def __init__(self):
        super().__init__()
        from dotenv import load_dotenv
        load_dotenv()

        self.alias = config.bot_name
        config.botlog.DiscordBotLogHandler.connect_client(self)
        self.token = os.getenv('DISCORD_TOKEN')
        self.guild_id = int(os.getenv('DISCORD_GUILD'))

        # Values initiated on_ready
        self.guild = None
        self.error_channel = None
        self.log_channel = None
        self.channels = {}

    def run(self):
        super().run(self.token)

    def send_log(self, msg):
        if self.log_channel is not None:
            asyncio.create_task(self.log_channel.send(msg))

    def send_error(self, msg):
        if self.error_channel is not None:
            asyncio.create_task(self.error_channel.send(msg))

    #########
    # Hooks #
    #########

    async def on_error(self, event, *args, **kwargs):
        ex_type = sys.exc_info()[0]

        logging.exception(f'Error on event: {event}')

        exception_lines = traceback.format_exception(*sys.exc_info())

        if self.error_channel is not None:
            await self.error_channel.send(''.join(exception_lines))

        if ex_type is InvalidConfigException:
            await self.logout()

    async def on_ready(self):
        # Find guild
        self.guild = self.get_guild(self.guild_id)
        if self.guild is None:
            raise InvalidConfigException("Discord server id is invalid", "DISCORD_GUILD")
        log.info(f'{self.user} is connected to the following guild: {self.guild.name}(id: {self.guild.id})')

        # Find error channel
        error_channel_id = get_channel_id("ERROR")
        if error_channel_id is not None:
            self.error_channel = self.get_channel(error_channel_id)
            if self.error_channel is None:
                raise InvalidConfigException("Error channel id is invalid", get_channel_env_var_name("ERROR"))
            if not is_text_channel(self.error_channel):
                raise InvalidConfigException(f"{self.error_channel.name}(id: {self.error_channel.id}) is not text channel", get_channel_env_var_name("ERROR"))
            log.info(f'Error channel: {self.error_channel.name}(id: {self.error_channel.id})')

        # Find log channel
        log_channel_id = get_channel_id("LOG")
        if log_channel_id is not None:
            self.log_channel = self.get_channel(log_channel_id)
            if self.log_channel is None:
                raise InvalidConfigException("Log channel id is invalid", get_channel_env_var_name("LOG"))
            if not is_text_channel(self.log_channel):
                raise InvalidConfigException(f"{self.log_channel.name}(id: {self.log_channel.id}) is not text channel", get_channel_env_var_name("LOG"))
            log.info(f'Log channel: {self.log_channel.name}(id: {self.log_channel.id})')

        # Resolve channels
        for channel_name in config.channels.keys():
            channel_num = config.channels[channel_name]
            channel_id = get_channel_id(channel_num)
            if channel_id is None:
                raise InvalidConfigException(f'Channel {channel_name}({channel_num}) id is absent', get_channel_env_var_name(channel_num))
            channel = self.get_channel(channel_id)
            if channel is None:
                raise InvalidConfigException(f'Channel {channel_name}({channel_num}) id is invalid', get_channel_env_var_name(channel_num))
            if not is_text_channel(channel):
                raise InvalidConfigException(f"{channel.name}(id: {channel.id}, alias: {channel_name}, num: {channel_num}) is not text channel", get_channel_env_var_name("ERROR"))
            self.channels[channel_name] = {
                "num": channel_num,
                "channel": channel
            }
            if channel_name in config.hooks["message"]:
                self.channels[channel_name]["on_message"] = config.hooks["message"][channel_name]
            else:
                self.channels[channel_name]["on_message"] = on_message_default

            log.info(f'Attached to {channel.name} (id: {channel.id}, alias:{channel_name}, num:{channel_num})')

        # Apply message hooks
        for channel_name in self.channels.keys():
            channel = self.channels[channel_name]
        
        if 'init' in config.hooks:
            hook = config.hooks['init']
            if not asyncio.iscoroutinefunction(hook):
                raise TypeError(f'{hook.__name__}: event registered must be a coroutine function')
            await hook(self)

    async def on_message(self, message):
        if message.author == self.user:
            return


async def on_message_default(client, message):
    pass

