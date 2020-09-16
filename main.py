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

import sys
import bot
import config
import logging.config

def main(argv):
    logging.config.dictConfig(config.LOGGER_CONFIG)
    discord_bot = bot.DiscordBot()
    discord_bot.run()

if __name__ == "__main__":
    main(sys.argv)
