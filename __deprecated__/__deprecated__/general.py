from abc import ABCMeta, abstractproperty
from binascii import hexlify
import hashlib
import os
import re
from socket import socket, AF_INET, SOCK_DGRAM
from time import time
import errno
from base import ProgrammingError
import itertools

__author__ = 'basca'

socket_connect_to = 'google.com'

PRIORITY_HIGH = 1
PRIORITY_LOW = 100

KBYTE = 1024
MBYTE = 1024 * KBYTE
GBYTE = 1024 * MBYTE


# ================================================================================================
#
# enum simulation
#
# ================================================================================================
def enum(**enums):
    """simulate enume pattern, from here: http://stackoverflow.com/questions/36932/whats-the-best-way-to-implement-an-enum-in-python
    example
    >>> Numbers = enum(ONE=1, TWO=2, THREE='three')
    >>> Numbers.ONE
    1
    >>> Numbers.TWO
    2
    >>> Numbers.THREE
    'three
    """
    return type('Enum', (), enums)


# ================================================================================================
#
# utility functions
#
# ================================================================================================
def get_hash(obj, hashfunc=hashlib.md5, ashex=False):
    _hash = hashfunc()
    _hash.update(str(obj))
    return hexlify(_hash.digest()) if ashex else _hash.digest()


def log_time(logger=None):
    def wrapper(func):
        def wrapper_func(*arg, **kwargs):
            t1 = time()
            res = func(*arg, **kwargs)
            t2 = time()
            msg = '[TIMEIT] %s took %.2f ms' % (func.func_name, (t2 - t1) * 1000)
            if logger and hasattr(logger, 'info'):
                logger.info(msg)
            else:
                print msg
            return res

        return wrapper_func

    return wrapper


def getpublicip():
    s = socket(AF_INET, SOCK_DGRAM)
    s.connect((socket_connect_to, 0))
    ipaddr = s.getsockname()[0]
    s.close()
    return ipaddr


def to_string(dataframe, materialized=False):
    if (hasattr(dataframe, 'materialized') and not dataframe.materialized) or not materialized:
        formatters = dict([(colname, lambda elem: hexlify(str(elem))) for colname in dataframe.columns])
        return dataframe.to_string(formatters=formatters)
    return dataframe.to_string()


def combinations(values):
    _all = []
    for i in xrange(len(values) + 1, 0, -1):
        _all.extend(list(itertools.combinations(values, i)))
    return _all


def identical_elements(lst):
    return lst.count(lst[0]) == len(lst)


def scale(value, vmin, vmax, a=0.0, b=1.0):
    """ scales value, between a and b given that min and max are known!
    http://stackoverflow.com/questions/5294955/how-to-scale-down-a-range-of-numbers-with-a-known-min-and-max-value"""
    return value if vmax == vmin else (float(b - a) * float(value - vmin)) / float(vmax - vmin) + a


def sort_natural(l):
    """ Sort the given list in the way that humans expect.
    from: http://www.codinghorror.com/blog/2007/12/sorting-for-humans-natural-sort-order.html """
    convert = lambda text: int(text) if text.isdigit() else text
    alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', key)]
    l.sort(key=alphanum_key)


def mkdir(path, mode=0777):
    try:
        os.mkdir(path, mode)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


# ================================================================================================
#
# abstract Registry class !
#
# ================================================================================================
class Registry(object):
    __metaclass__ = ABCMeta
    # the actual registry, needs to be a dict ...
    __registry__ = abstractproperty()
    # the baseclass of the element (by default it's object), extend with your own!
    __baseitemclass__ = object

    @classmethod
    def instance(cls):
        if not hasattr(cls, "_instance"):
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        assert isinstance(self.__registry__, dict), '`__registry__` is not a dict!'

    def __getitem__(self, name):
        try:
            return self.__registry__[name]
        except:
            raise ProgrammingError('%s not registered, valid options are :%s' % (name, str(self.__registry__)))

    def __setitem__(self, name, item_class):
        assert issubclass(item_class,
                          self.__baseitemclass__), '`item_class` not a subclass of %s' % self.__baseitemclass__.__name__
        self.__registry__[name] = item_class