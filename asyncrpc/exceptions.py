from inspect import isclass
import sys
from traceback import format_exception
import socket
import errno
from abc import ABCMeta, abstractproperty

__author__ = 'basca'


class CommandNotFoundException(Exception):
    pass


class InvalidInstanceId(Exception):
    pass


class InvalidStateException(Exception):
    pass


class RpcServerNotStartedException(Exception):
    pass


class RpcRemoteException(Exception):
    def __init__(self, message, error, remote_type=None):
        super(RpcRemoteException, self).__init__(message.message if isinstance(message, BaseException) else message)
        self.error = error
        self.remote_type = remote_type.__name__ if isclass(remote_type) else remote_type
        if not self.remote_type and isinstance(message, BaseException):
            self.remote_type = message.__class__.__name__

    def __str__(self):
        return """
Remote RPC exception: {0}
{1}Remote {2}
        """.format(self.message, '' if not self.remote_type else 'Remote Exception: {0}\n'.format(self.remote_type),
                   self.error).strip()


_EXCEPTIONS = {ex.__name__: ex for ex in
               [CommandNotFoundException, InvalidInstanceId, InvalidStateException, RpcServerNotStartedException]}


class HTTPRpcNoBodyException(RpcRemoteException):
    def __init__(self, address, error):
        super(HTTPRpcNoBodyException, self).__init__("HTTP request body is None on: {0}".format(address), error)


def handle_exception(address, remote_exception_description):
    if not isinstance(remote_exception_description, dict):
        raise ValueError('remote_exception_description must be a dictionary')
    remote_type = remote_exception_description.get('type', None)

    if remote_type and remote_type in _EXCEPTIONS:
        message = 'address:{0}, message:{1}\n{2}'.format(
            address, remote_exception_description['message'], remote_exception_description['traceback'])
        raise _EXCEPTIONS[remote_type](message)
    raise RpcRemoteException(remote_exception_description['message'],
                             remote_exception_description['traceback'],
                             remote_type=remote_type)


