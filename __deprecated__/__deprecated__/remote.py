try:
    __import__('builtins')
except ImportError:
    import __builtin__ as builtins
import sys
from traceback import format_exception
from collections import namedtuple
import socket
import errno
from base import *
from general import Registry

__author__ = 'basca'

# noinspection PyBroadException
def _isbuiltin_exception(e):
    try:
        return issubclass(e, BaseException)
    except:
        pass
    return False


BUILTIN_EXCEPTIONS = set(e for e in vars(builtins).values() if _isbuiltin_exception(e))
BUILTIN_EXCEPTIONS_NAMES = set(e.__name__ for e in BUILTIN_EXCEPTIONS)


class RemoteExceptionDescriptor(object):
    def __init__(self, kind=None, name=None, args=None, traceback=None):
        self.kind = kind
        self.name = name
        self.args = args
        self.traceback = traceback


EXCEPTION_UNKNOWN = -1
EXCEPTION_REMOTE = 1
EXCEPTION_CONNECTION = 2


class RemoteExceptionsRegistry(Registry):
    __baseitemclass__ = AvaRemoteException
    __registry__ = {
        EXCEPTION_REMOTE: AvaRemoteException,
        EXCEPTION_CONNECTION: ConnectionDownException,
    }


def __exception_kind__(exc_type, exc_value):
    """returns the internal Avalanche type of an exception"""
    exc_kind = EXCEPTION_UNKNOWN
    if exc_type is socket.error and isinstance(exc_value.args, tuple):
        if exc_value.args[0] in [errno.ECONNREFUSED,
                                 errno.ECONNABORTED,
                                 errno.ECONNRESET]:
            exc_kind = EXCEPTION_CONNECTION
    elif exc_type in [AvaRemoteException, ConnectionDownException]:
        exc_kind = EXCEPTION_REMOTE
    return exc_kind


def __exception_name__(exc_type):
    """returns the exception's name """
    if exc_type in BUILTIN_EXCEPTIONS or exc_type in [AvaRemoteException, ConnectionDownException]:
        return exc_type.__name__
    return repr(exc_type)


def current_error():
    """ returns information about the most current exception,
    usefull for the server side reporting of exceptions """
    exc_type, exc_value, exc_traceback = sys.exc_info()
    return RemoteExceptionDescriptor(
        kind=__exception_kind__(exc_type, exc_value),
        name=__exception_name__(exc_type),
        args=exc_value.args,
        traceback=format_exception(exc_type, exc_value, exc_traceback))


def get_exception(exc_decriptor, host):
    if not isinstance(exc_decriptor, RemoteExceptionDescriptor):
        exc = MalformedResponseException(exc_decriptor, host=host)

    elif exc_decriptor.name in BUILTIN_EXCEPTIONS_NAMES:
        exc = getattr(builtins, exc_decriptor.name)()
        exc.args = exc_decriptor.args

    else:
        ExceptionClass = RemoteExceptionsRegistry.instance()[exc_decriptor.kind]
        exc = ExceptionClass(exc_decriptor.name,
                             exc_decriptor.args, exc_decriptor.traceback, host=host)
    return exc