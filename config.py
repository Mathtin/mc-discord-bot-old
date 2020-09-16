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
import util

BOT_NAME = "MC Manager"

CONTROL_PREFIX = "!"

PERSIST_WHITELIST_PATH = "persist_whitelist.json"

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
            '()': util.DiscordBotLogHandler,
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
    "error": 2,
    "control": 2,


    # User defined

    "profile": 2
}

hooks = {
    "init": 'manager.init',

    "message": {
        "new": {
            "profile": 'manager.new_profile'
        },
        "edit": {
            "profile": 'manager.edit_profile'
        },
        "delete": {
            "profile": 'manager.delete_profile'
        },
    },

    "member": {
        'remove': 'manager.user_left'
    },

    "control": {
        "send": 'manager.send_to_sink',
        "ping": 'manager.ping',
        "reload": 'manager.reload',
        "db": 'manager.show_db',
        "pdb": 'manager.show_persist_db',
        "pdb-add": 'manager.add_persist_profile',
        "pdb-rm": 'manager.remove_persist_profile',
    }
}

roles = {
    "admin": ["Admin"]
}

manager = {
    "whitelist": {
        "upload": False,
        "reload": False,
    },

    "profile": {
        "update": {
            "old": {
                "delete": False
            }
        },
        "invalid": {
            "ign": {
                "delete": False,
                "dm": False
            },
            "duplicate": {
                "delete": False,
                "dm": False
            },
            "default": {
                "delete": False,
                "dm": False
            },
        },
        "deprecated": {
            "delete": False,
            "whitelist": False
        }
    }
}
