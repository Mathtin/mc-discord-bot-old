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

from util import * 
import json
import config

log = logging.getLogger('database')

class DatabaseContext(object):
    """
    Basic database context implementation
    """

    def __init__(self, name):
        
        self.name = name
        self.tables = {}
        self.indexes = {}
        self.path = config_path(f"db.{name}.path", None)

        table_conf = config_path(f"db.{name}.tables", {})
        index_conf = config_path(f"db.{name}.indexes", {})

        for table in table_conf:
            self.tables[table] = []

            if table in index_conf:
                self.indexes[table] = {}
                for index_name in index_conf[table]:
                    self.indexes[table][index_name] = {}
            else:
                self.indexes[table] = None

    def clear(self):
        for table in self.tables:
            self.tables[table] = []
        for table in self.indexes:
            if self.indexes[table] is None:
                continue
            for index_name in self.indexes[table]:
                self.indexes[table][index_name] = {}

    def table(self, name):
        return TableContext(name, self.tables[name], self.indexes[name])

    def build_index(self):
        for table_name in self.indexes:
            self.table(table_name).build_index()

    def save(self):
        with open(self.path, "w") as f:
            json.dump(self.tables, f)

    def load(self):
        if not os.path.exists(self.path):
            self.clear()
            self.save()
        try:
            with open(self.path, "r") as f:
                self.tables = json.load(f)
                self.build_index()
        except json.decoder.JSONDecodeError:
            log.error("Failed to load persist database, removing invalid data")
            self.clear()
            self.save()

    def __getitem__(self, table_name):
        if table_name not in self.tables:
            raise KeyError(f'No such table "{table_name}"')
        return self.table(table_name)

    def __getattr__(self, table_name):
        if table_name not in self.tables:
            raise AttributeError(f'No such table "{table_name}"')
        return self.table(table_name)

    def __iter__(self):
        return DatabaseContextIterator(self)

    def __contains__(self, table_name):
        return table_name in self.tables

class DatabaseContextIterator(object):
    """
    Basic database context iterator implementation
    """
    def __init__(self, db):
       self._db = db
       self._iter = db.tables.__iter__()
   
    def __next__(self):
        table_name = self._iter.__next__()
        return self._db.table(table_name)

class TableContext(object):
    """
    Basic database context implementation
    """

    def __init__(self, name: str, table: list, indexes: dict):
        self.name = name
        self.table = table
        self.indexes = indexes

    def __add_to_index(self, row: dict):
        if self.indexes is None:
            return
        for column_name in self.indexes:
            index = self.indexes[column_name]
            value = row[column_name]
            if value not in index:
                index[value] = [row]
            else:
                index[value].append(row)

    def __remove_from_index(self, row: dict):
        if self.indexes is None:
            return
        for column_name in self.indexes:
            index = self.indexes[column_name]
            value = row[column_name]
            if value not in index:
                return
            rows = index[value]
            for i in range(len(rows)):
                if row is rows[i]:
                    del rows[i]
                    if len(rows) == 0:
                        del index[value]
                    return

    def __enumerate(self):
        for i, row in enumerate(self.table):
            row['id'] = i

    def build_index(self):
        if self.indexes is None:
            return
        for column in self.indexes:
            self.indexes[column] = {}
        for row in self.table:
            self.__add_to_index(row)

    def add(self, row: dict):
        row['id'] = self.size()
        self.table.append(row)
        self.__add_to_index(row)

    def remove(self, row: dict):
        id = row['id']
        table_size = len(self.table)
        if id < 0 or id >= table_size:
            raise IndexError(f'No such id {id} in table "{self.name}"({table_size})')
        del self.table[id]
        self.__remove_from_index(row)
        self.__enumerate()

    def __getitem__(self, id: int):
        table_size = len(self.table)
        if id < 0 or id >= table_size:
            raise IndexError(f'No such id {id} in table "{self.name}"({table_size})')
        return self.table[id]

    def __getattr__(self, column: str):
        if column not in self.indexes:
            raise AttributeError(f'No such column index "{column}" for table "{self.name}"')
        return self.indexes[column]

    def __iter__(self):
       return self.table.__iter__()

    def __contains__(self, row: dict):
        id = row['id']
        return 0 <= id < len(self.table) and row is self.table[id]

    def size(self):
        return len(self.table)

    def __len__(self):
        return self.size()


