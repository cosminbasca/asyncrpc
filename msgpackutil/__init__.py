import hooks
from base import HOOKS
from msgpack import packb, unpackb

__author__ = 'basca'
_pack_hook = HOOKS.pack
_unpack_hook = HOOKS.unpack


def dumps(value):
    return packb(value, default=_pack_hook)


def loads(value_bytes):
    return unpackb(value_bytes, object_hook=_unpack_hook)

