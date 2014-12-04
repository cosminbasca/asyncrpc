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
import msgpack
from warnings import warn

__author__ = 'basca'

# ----------------------------------------------------------------------------------------------------------------------
#
# internals
#
# ----------------------------------------------------------------------------------------------------------------------
__default = 'msgpack'
__entrypoint = 'asyncrpc.messaging'

__CURRENT = __default
__MESSAGING_LIBS = {}

# ----------------------------------------------------------------------------------------------------------------------
#
# api
#
# ----------------------------------------------------------------------------------------------------------------------
MessagingLib = namedtuple('MessagingLib', ['loads', 'dumps'])

def register(lib_id, lib_loads, lib_dumps):
    global __MESSAGING_LIBS
    __MESSAGING_LIBS[lib_id] = MessagingLib(lib_loads, lib_dumps)

def select(lib_id):
    global __CURRENT, __MESSAGING_LIBS
    if lib_id in __MESSAGING_LIBS:
        __CURRENT = lib_id

def current():
    global __CURRENT
    return __CURRENT

def loads(msg):
    global __MESSAGING_LIBS, __CURRENT
    return __MESSAGING_LIBS[__CURRENT].loads(msg)


def dumps(obj):
    global __MESSAGING_LIBS, __CURRENT
    return __MESSAGING_LIBS[__CURRENT].dumps(obj)


def registered_libs():
    global __MESSAGING_LIBS
    return __MESSAGING_LIBS.keys()

# ----------------------------------------------------------------------------------------------------------------------
#
# looking for external entrypoints defining messaging libs
#
# ----------------------------------------------------------------------------------------------------------------------
try:
    from pkg_resources import iter_entry_points
except ImportError:
    pass # pkg_resources not found ... (going with default implementations)
else:
    for entrypoint in iter_entry_points(__entrypoint):
        messaging_lib = entrypoint.load()
        if hasattr(messaging_lib, 'loads') and hasattr(messaging_lib, 'dumps'):
            register(entrypoint.name, messaging_lib.loads, messaging_lib.dumps)
        else:
            warn('messaging lib registered for %s does not have any loads and dumps methods', entrypoint.name)

# ----------------------------------------------------------------------------------------------------------------------
#
# register the builtin serialization libs
#
# ----------------------------------------------------------------------------------------------------------------------
register('cPickle', cPickle.loads, cPickle.dumps)
register('json', json.loads, json.dumps)
register('msgpack', msgpack.loads, msgpack.dumps)
