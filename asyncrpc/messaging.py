import cPickle
import json
import msgpackutil
from collections import namedtuple

__author__ = 'basca'

__all__ = ['register', 'select', 'loads', 'dumps', 'registered_libs']

MessagingLib = namedtuple('MessagingLib', ['loads', 'dumps'])

__LIBS__ = {
    'cPickle': MessagingLib(cPickle.loads, cPickle.dumps),
    'json': MessagingLib(json.loads, json.dumps),
    'msgpack++': MessagingLib(msgpackutil.loads, msgpackutil.dumps)
}

# __CURRENT__ = 'cPickle'
__CURRENT__ = 'msgpack++'


def register(lib_id, lib_loads, lib_dumps):
    global __LIBS__
    __LIBS__[lib_id] = MessagingLib(lib_loads, lib_dumps)


def select(lib_id):
    global __CURRENT__, __LIBS__
    if lib_id in __LIBS__:
        __CURRENT__ = lib_id


def loads(msg):
    global __LIBS__, __CURRENT__
    return __LIBS__[__CURRENT__].loads(msg)


def dumps(obj):
    global __LIBS__, __CURRENT__
    return __LIBS__[__CURRENT__].dumps(obj)


def registered_libs():
    global __LIBS__
    return __LIBS__.keys()
