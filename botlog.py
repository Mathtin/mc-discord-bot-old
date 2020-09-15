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
            msg = self.format(record)
            self.client.send_log(msg)
        except RecursionError:
            raise
        except Exception:
            self.handleError(record)
