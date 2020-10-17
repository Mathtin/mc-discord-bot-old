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
import logging
import discord
import config

from util import *

from dotenv import load_dotenv
load_dotenv()

log = logging.getLogger('mc-discord-bot')

class DiscordBot(discord.Client):

    def __init__(self):
        intents = discord.Intents.none()
        intents.guilds = True
        intents.members = True
        intents.messages = True

        super().__init__(intents=intents)

        self.alias = config.BOT_NAME
        DiscordBotLogHandler.connect_client(self)
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
        self.member_hooks = {}

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
        if ex_type is NotCoroutineException:
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

            if (hook_name := config_path(f"hooks.message.{channel_name}.new", None)) is not None:
                hook = get_module_element(hook_name)
                check_coroutine(hook)
                sink["on_message"] = hook

            if (hook_name := config_path(f"hooks.message.{channel_name}.edit", None)) is not None:
                hook = get_module_element(hook_name)
                check_coroutine(hook)
                sink["on_message_edit"] = hook

            if (hook_name := config_path(f"hooks.message.{channel_name}.delete", None)) is not None:
                hook = get_module_element(hook_name)
                check_coroutine(hook)
                sink["on_message_delete"] = hook

            log.info(f'Attached to {channel.name} as {channel_name} channel (id: {channel.id}, num:{channel_num})')

        # Attach control hooks
        control_hooks = config_path("hooks.control.commands", {})
        for cmd in control_hooks:
            hook = get_module_element(control_hooks[cmd])
            check_coroutine(hook)
            self.commands[cmd] = hook

        if (hook_name := config_path(f"hooks.member.remove", None)) is not None:
            hook = get_module_element(hook_name)
            check_coroutine(hook)
            self.member_hooks["remove"] = hook
        
        if (hook_name := config_path(f"hooks.init", None)) is not None:
            hook = get_module_element(hook_name)
            check_coroutine(hook)
            await hook(self)
        
        print(config_path(f"EGG_DONE_MESSAGE", "bot initialized successfully"))

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

    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        sinks = self.get_attached_sinks(payload.channel_id)
        if sinks is None:
            return

        channel = self.get_channel(payload.channel_id)

        msg = await channel.fetch_message(payload.message_id)

        # ingore own messages
        if msg.author.id == self.user.id:
            return

        for sink in sinks:
            if "on_message_edit" not in sink:
                continue
            await sink["on_message_edit"](self, msg)

    async def on_raw_message_delete(self, payload: discord.RawMessageUpdateEvent):
        sinks = self.get_attached_sinks(payload.channel_id)
        if sinks is None:
            return

        for sink in sinks:
            if "on_message_delete" not in sink:
                continue
            await sink["on_message_delete"](self, payload.message_id)

    async def on_member_remove(self, member: discord.Member):

        # ingore any foreign members
        if member.guild.id != self.guild.id:
            return
        
        if 'remove' in self.member_hooks:
            await self.member_hooks["remove"](self, member)

    async def on_control_message(self, message: discord.Message):
        argv = parse_control_message(message)

        if argv is None or len(argv) == 0:
            return
            
        cmd_name = argv[0]

        if cmd_name == "help":
            help_lines = []
            for cmd in self.commands:
                hook = self.commands[cmd]
                help_lines.append(build_cmdcoro_usage(cmd, hook.or_cmdcoro))
            help_msg = '\n'.join(help_lines)
            await message.channel.send(f'Available commands:\n`######------######\n{help_msg}\n######------######`')
            return

        if cmd_name not in self.commands:
            await message.channel.send("Unknown command")
            return
        
        await self.commands[cmd_name](self, message, argv)
