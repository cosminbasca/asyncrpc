import traceback

try:
    __import__('builtins')
except ImportError:
    import __builtin__ as builtins
import sys
from traceback import format_exception
import socket
import errno
from abc import ABCMeta, abstractproperty

__all__ = ['RemoteExceptionDescriptor', 'RpcServerException', 'MalformedResponseException', 'ConnectionDownException',
           'ConnectionClosedException', 'RpcRemoteException', 'current_error', 'get_exception']

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

    def __str__(self):
        return '''
kind: {0}
name: {1}
args: {2}
traceback:
{3}
'''.format(self.kind, self.name, self.args, ''.join(self.traceback))

EXCEPTION_UNKNOWN = -1
EXCEPTION_REMOTE = 1
EXCEPTION_CONNECTION = 2


class InvalidInstanceId(Exception):
    pass


class InvalidType(Exception):
    pass


class InvalidStateException(Exception):
    pass


class RpcServerNotStartedException(Exception):
    pass


class RpcServerException(Exception):
    __metaclass__ = ABCMeta
    __description__ = abstractproperty

    def __init__(self, args, address=None):
        super(RpcServerException, self).__init__(args)
        self.address = address

    def __str__(self):
        return '"{0}" exception on {1}, reason: {2}'.format(self.__description__, self.address, self.args)


class MalformedResponseException(RpcServerException):
    __description__ = 'Malformed response'


class ConnectionClosedException(RpcServerException):
    __description__ = 'Connection closed'


class RpcRemoteException(RpcServerException):
    __description__ = 'RPC Remote Exception'

    def __init__(self, name, args, traceback, host=None):
        super(RpcServerException, self).__init__(args, host=host)
        self.name = name
        self.traceback = traceback

    def __str__(self):
        return "{0}, name: {1}, traceback:\n{2}".format(super(RpcRemoteException, self).__str__(), self.name,
                                                        self.traceback)


class ConnectionDownException(RpcRemoteException):
    __description__ = '{0}: connection down'.format(RpcRemoteException.__description__)


__REMOTE_EXCEPTIONS__ = {
    EXCEPTION_REMOTE: RpcRemoteException,
    EXCEPTION_CONNECTION: ConnectionDownException,
}


def __exception_kind__(exc_type, exc_value):
    exc_kind = EXCEPTION_UNKNOWN
    if exc_type is socket.error and isinstance(exc_value.args, tuple):
        if exc_value.args[0] in [errno.ECONNREFUSED,
                                 errno.ECONNABORTED,
                                 errno.ECONNRESET]:
            exc_kind = EXCEPTION_CONNECTION
    elif exc_type in [RpcRemoteException, ConnectionDownException]:
        exc_kind = EXCEPTION_REMOTE
    return exc_kind


def __exception_name__(exc_type):
    if exc_type in BUILTIN_EXCEPTIONS or exc_type in [RpcRemoteException, ConnectionDownException]:
        return exc_type.__name__
    return repr(exc_type)


def current_error():
    exc_type, exc_value, exc_traceback = sys.exc_info()
    return RemoteExceptionDescriptor(
        kind=__exception_kind__(exc_type, exc_value),
        name=__exception_name__(exc_type),
        args=exc_value.args,
        traceback=format_exception(exc_type, exc_value, exc_traceback))


def get_exception(exc_decriptor, address):
    if not isinstance(exc_decriptor, RemoteExceptionDescriptor):
        exc = MalformedResponseException(exc_decriptor, address=address)
    elif exc_decriptor.name in BUILTIN_EXCEPTIONS_NAMES:
        exc = getattr(builtins, exc_decriptor.name)()
        exc.args = exc_decriptor.args
    else:
        ExceptionClass = __REMOTE_EXCEPTIONS__[exc_decriptor.kind]
        exc = ExceptionClass(exc_decriptor.name, exc_decriptor.args, exc_decriptor.traceback, host=address)
    return exc