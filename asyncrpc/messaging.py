#
# author: Cosmin Basca
#
# Copyright 2010 University of Zurich
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import cPickle
import json
from collections import namedtuple

__author__ = 'basca'

__all__ = ['register', 'select', 'loads', 'dumps', 'registered_libs']

MessagingLib = namedtuple('MessagingLib', ['loads', 'dumps'])

__LIBS__ = {
    'cPickle': MessagingLib(cPickle.loads, cPickle.dumps),
    'json': MessagingLib(json.loads, json.dumps),
}

__CURRENT__ = 'cPickle'


def register(lib_id, lib_loads, lib_dumps):
    global __LIBS__
    __LIBS__[lib_id] = MessagingLib(lib_loads, lib_dumps)


def select(lib_id):
    global __CURRENT__, __LIBS__
    if lib_id in __LIBS__:
        __CURRENT__ = lib_id

def current():
    global __CURRENT__
    return __CURRENT__

def loads(msg):
    global __LIBS__, __CURRENT__
    return __LIBS__[__CURRENT__].loads(msg)


def dumps(obj):
    global __LIBS__, __CURRENT__
    return __LIBS__[__CURRENT__].dumps(obj)


def registered_libs():
    global __LIBS__
    return __LIBS__.keys()
