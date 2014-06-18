import hooks
from base import HOOKS
from msgpack import packb as _packb, unpackb as _unpackb

__author__ = 'basca'
_pack_hook = HOOKS.pack
_unpack_hook = HOOKS.unpack

__all__ = ['dumps', 'loads', 'packb', 'unpackb']


def dumps(value):
    return _packb(value, default=_pack_hook)


def loads(value_bytes):
    return _unpackb(value_bytes, object_hook=_unpack_hook)


packb = dumps
unpackb = loads
