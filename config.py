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

import logging.config
import botlog

BOT_NAME = "ECC MC Manager"

CONTROL_PREFIX = "!"

LOGGER_CONFIG = { 
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': { 
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        },
    },
    'handlers': { 
        'console': { 
            'level': 'INFO',
            'formatter': 'standard',
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stderr',
        },
        'file': { 
            'level': 'INFO',
            'formatter': 'standard',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'mc-discord-bot.log',
            'maxBytes': 1024 * 1024 * 10,
            'backupCount': '3'
        },
        'discord-channel': { 
            'level': 'WARN',
            'formatter': 'standard',
            '()': botlog.DiscordBotLogHandler,
            'bot': BOT_NAME
        },
    },
    'loggers': {
        'mc-discord-bot': {
            'handlers': ['console','file', 'discord-channel'],
            'level': 'INFO'
        },
        'manager-hooks': {
            'handlers': ['console','file', 'discord-channel'],
            'level': 'INFO'
        }
    } 
}

channels = {

    # Special

    # "log": 0,
    "error": 0,
    "control": 0,


    # User defined

    "profile": 0
}

hooks = {
    "init": 'manager.init',

    "message": {
        "profile": 'manager.new_profile'
    },

    "control": {
        "db": 'manager.show_db',
        "send": 'manager.send_to_sink',
    }
}

roles = {
    "admin": ["Headquarter"]
}
