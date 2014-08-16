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
        """.format(self.address, self.message, '' if not self.remote_type else 'Remote Exception: {0}\n'.format(self.remote_type),
                   self.error).strip()


_EXCEPTIONS = {ex.__name__: ex for ex in
               [CommandNotFoundException, InvalidInstanceId, InvalidStateException, RpcServerNotStartedException]}


class HTTPRpcNoBodyException(RpcRemoteException):
    def __init__(self, address, error):
        super(HTTPRpcNoBodyException, self).__init__("HTTP request body is empty", address, error)


def handle_exception(address, remote_exception_description):
    if not isinstance(remote_exception_description, dict):
        raise ValueError('remote_exception_description must be a dictionary')
    remote_type = remote_exception_description.get('type', None)

    if remote_type and remote_type in _EXCEPTIONS:
        message = 'Remote address:{0}, error:{1}\n{2}'.format(
            remote_exception_description['address'], remote_exception_description['message'],
            remote_exception_description['traceback'])
        raise _EXCEPTIONS[remote_type](message)
    raise RpcRemoteException(remote_exception_description['message'],
                             remote_exception_description['address'],
                             remote_exception_description['traceback'],
                             remote_type=remote_type)


