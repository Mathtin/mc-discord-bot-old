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

""" Username to UUID
Converts a Minecraft username to it's UUID equivalent.

Uses the official Mojang API to fetch player data.
"""

### Import necessary modules
import http.client
import json
from uuid import UUID

def is_valid_minecraft_username(username):
    """https://help.mojang.com/customer/portal/articles/928638-minecraft-usernames"""
    allowed_chars = 'abcdefghijklmnopqrstuvwxyz1234567890_'
    allowed_len = [3, 16]

    username = username.lower()

    if len(username) < allowed_len[0] or len(username) > allowed_len[1]:
        return False

    for char in username:
        if char not in allowed_chars:
            return False

    return True

def is_valid_mojang_uuid(uuid):
    """https://minecraft-de.gamepedia.com/UUID"""
    allowed_chars = '0123456789abcdef'
    allowed_len = 32

    uuid = uuid.lower()

    if len(uuid) != 32:
        return False

    for char in uuid:
        if char not in allowed_chars:
            return False

    return True

### Main class
class GetPlayerData:
    def __init__(self, identifier, timestamp=None):
        self.valid = True
        """
            Get the UUID of the player.

            Parameters
            ----------
            username: string
                The known minecraft username
            timestamp : long integer (optional)
                The time at which the player used this name, expressed as a Unix timestamp.
        """

        # Handle the timestamp
        get_args = ""
        if timestamp is not None:
            get_args = "?at=" + str(timestamp)

        # Build the request path based on the identifier
        req = ""
        if is_valid_minecraft_username(identifier):
            req = "/users/profiles/minecraft/" + identifier + get_args
        elif is_valid_mojang_uuid(identifier):
            req = "/user/profiles/" + identifier + "/names" + get_args
        else:
            self.valid = False

        # Proceed only, when the identifier was valid
        if self.valid:
            # Request the player data
            http_conn = http.client.HTTPSConnection("api.mojang.com");
            http_conn.request("GET", req,
                headers={'User-Agent':'https://github.com/clerie/mcuuid', 'Content-Type':'application/json'});
            response = http_conn.getresponse().read().decode("utf-8")

            # In case the answer is empty, the user dont exist
            if not response:
                self.valid = False
            # If there is an answer, fill out the variables
            else:
                # Parse the JSON
                json_data = json.loads(response)

                ### Handle the response of the different requests on different ways
                # Request using username
                if is_valid_minecraft_username(identifier):
                    # The UUID
                    self.uuid = json_data['id']
                    # The username written correctly
                    self.username = json_data['name']
                #Request using UUID
                elif is_valid_mojang_uuid(identifier):
                    # The UUID
                    self.uuid = identifier

                    current_name = ""
                    current_time = 0

                    # Getting the username based on timestamp
                    for name in json_data:
                        # Prepare the JSON
                        # The first name has no change time
                        if 'changedToAt' not in name:
                            name['changedToAt'] = 0

                        # Get the right name on timestamp
                        if current_time <= name['changedToAt'] and (timestamp is None or name['changedToAt'] <= timestamp):
                            current_time = name['changedToAt']
                            current_name = name['name']


                    # The username written correctly
                    self.username = current_name
                self.uuid = UUID(self.uuid)
