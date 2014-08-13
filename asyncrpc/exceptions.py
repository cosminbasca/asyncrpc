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
    def __init__(self, message, error):
        super(RpcRemoteException, self).__init__(message.message if isinstance(message, BaseException) else message)
        self.error = error

    def __str__(self):
        return """
Remote rpc exception: {0}
remote exception:
{1}
        """.format(self.message, self.error).strip()


_EXCEPTIONS = {ex.__name__: ex for ex in
               [CommandNotFoundException, InvalidInstanceId, InvalidStateException, RpcServerNotStartedException]}


class HTTPRpcNoBodyException(RpcRemoteException):
    def __init__(self, address, error):
        super(HTTPRpcNoBodyException, self).__init__("HTTP request body is None on: {0}".format(address), error)


def handle_exception(address, remote_exception_description):
    if not isinstance(remote_exception_description, dict):
        raise ValueError('remote_exception_description must be a dictionary')
    ex_type = remote_exception_description.get('type', None)
    exception = None
    message = 'address:{0}, message:{1}\n{2}'.format(
        address, remote_exception_description['message'], remote_exception_description['traceback'])
    if ex_type:
        _Exception = _EXCEPTIONS.get(ex_type, None)
        if _Exception:
            exception = _Exception(message)
        elif ex_type == RpcRemoteException.__name__:
            exception = RpcRemoteException(remote_exception_description['message'],
                                           remote_exception_description['traceback'])
        else:
            exception = Exception(message)
    else:
        exception = Exception(message)
    raise exception

