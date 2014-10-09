from inspect import isclass
import sys
from traceback import format_exception
import socket
import errno
from abc import ABCMeta, abstractproperty
import traceback

__author__ = 'basca'


class ErrorMessage(object):
    def __init__(self, message, error_type=None, stacktrace=None, address=None):
        self.message = message
        self.error_type = error_type
        self.stacktrace = stacktrace
        self.address = address

    @staticmethod
    def from_exception(e, address=None):
        return ErrorMessage(e.message, error_type=e.__class__.__name__, stacktrace=traceback.format_exc(),
                            address=address)

    def __getstate__(self):
        return self.message, self.error_type, self.stacktrace, self.address

    def __setstate__(self, state):
        self.message, self.error_type, self.stacktrace, self.address = state


class CommandNotFoundException(Exception):
    pass


class InvalidInstanceId(Exception):
    pass


class InvalidTypeId(Exception):
    pass


class InvalidStateException(Exception):
    pass


class RpcServerNotStartedException(Exception):
    pass


class BackgroundRunnerException(Exception):
    def __init__(self, message, ex_type, ex_class, tb):
        super(BackgroundRunnerException, self).__init__(message)
        self._type = ex_type
        self._class = ex_class
        self._tb = ''.join(traceback.format_list(tb)) if tb else ''

    def __str__(self):
        return """
BackgroundRunnerException: {0}
Type: {1}, Class: {2}
{3}
        """.format(self.message, self._type, self._class, self._tb)


class RpcRemoteException(Exception):
    def __init__(self, message, address, error, remote_type=None):
        super(RpcRemoteException, self).__init__(message.message if isinstance(message, BaseException) else message)
        self.error = error
        self.address = address
        self.remote_type = remote_type.__name__ if isclass(remote_type) else remote_type
        if not self.remote_type and isinstance(message, BaseException):
            self.remote_type = message.__class__.__name__

    def __str__(self):
        return """
Remote RPC exception on {0}: {1}
{2}Remote {3}
        """.format(self.address, self.message,
                   '' if not self.remote_type else 'Remote Exception: {0}\n'.format(self.remote_type),
                   self.error).strip()


_EXCEPTIONS = {ex.__name__: ex for ex in
               [CommandNotFoundException, InvalidInstanceId, InvalidStateException, RpcServerNotStartedException]}


class HTTPRpcNoBodyException(RpcRemoteException):
    def __init__(self, address, error):
        super(HTTPRpcNoBodyException, self).__init__("HTTP request body is empty", address, error)


def handle_exception(error_message):
    if not isinstance(error_message, ErrorMessage):
        raise ValueError('error_message must be an ErrorMessage')
    if error_message.error_type and error_message.error_type in _EXCEPTIONS:
        message = 'Remote address:{0}, error:{1}\n{2}'.format(error_message.address, error_message.message,
                                                              error_message.stacktrace)
        raise _EXCEPTIONS[error_message.error_type](message)
    raise RpcRemoteException(error_message.message, error_message.address, error_message.stacktrace,
                             remote_type=error_message.error_type)


