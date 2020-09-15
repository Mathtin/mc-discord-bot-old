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

log = logging.getLogger('manager-hooks')

async def init(client):
    log.info("Hello world")
    raise Exception("HAHA")

async def test_message(client, event, *args, **kwargs):
    log.info("test_channel_message_hook")
    log.info(event)
    log.info(args)
    log.info(kwargs)
