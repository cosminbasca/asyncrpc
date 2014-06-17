import hooks
from base import HOOKS
from msgpack import packb, unpackb

__author__ = 'basca'

dumps = lambda value: packb(value, default=HOOKS.pack)
loads = lambda value_bytes: unpackb(value_bytes, default=HOOKS.unpack)

