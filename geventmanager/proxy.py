from abc import ABCMeta, abstractproperty
import socket
import errno
import traceback
from gevent import sleep as gevent_sleep
from geventhttpclient.connectionpool import ConnectionPool
from time import sleep
from msgpackutil import dumps, loads
from rpcsocket import GeventRpcSocket, InetRpcSocket, RpcSocket
from log import get_logger
from exceptions import get_exception


__author__ = 'basca'

__all__ = ['Proxy', 'DispatcherProxy', 'InetProxy', 'GeventProxy', 'GeventPooledProxy']


def _command(name):
    return '#cmd:{0}#'.format(name)


_CMD_SHUTDOWN = _command('shutdown')
_CMD_PING = _command('ping')
_CMD_CLOSE_CONN = _command('close_conn')
_INIT_ROBJ = _command('init_robj')

_RETRY_WAIT = 0.025

# ----------------------------------------------------------------------------------------------------------------------
#
# base Rpc proxy
#
# ----------------------------------------------------------------------------------------------------------------------
class Proxy(object):
    __metaclass__ = ABCMeta

    RpcSocketClass = abstractproperty

    def get_socket(self):
        sock = self.RpcSocketClass()
        if not isinstance(sock, RpcSocket):
            raise ValueError('socket is not an RpcSocket instance!')
        return sock

    def __init__(self, address, retries=2000, **kwargs):
        if isinstance(address, (tuple, list)):
            host, port = address
        elif isinstance(address, (str, unicode)):
            host, port = address.split(':')
            port = int(port)
        else:
            raise ValueError('host, must be either a tuple/list or string of the name:port form')
        self._address = (host, port)
        self._retries = retries
        self._log = get_logger(self.__class__.__name__)

    @property
    def port(self):
        return self._address[1]

    @property
    def host(self):
        return self._address[0]

    @property
    def address(self):
        return self._address

    def __getattr__(self, func):
        def func_wrapper(*args, **kwargs):
            _sock = None
            result = None
            try:
                retries = 0
                while retries < self._retries:
                    # wait until a connection is available from the server!
                    try:
                        _sock = self._init_socket()
                        _sock.setblocking(1)
                        _sock.write(dumps((func, args, kwargs)))

                        result = self._receive_result(_sock)
                        break
                    except socket.error, err:
                        if err[0] == errno.ECONNRESET or err[0] == errno.EPIPE:
                            # Connection reset by peer, or an error on the pipe...
                            self._log.debug('rpc retry ...')
                            if _sock:
                                self._release_socket(_sock)
                            del _sock
                            _sock = None
                            self.wait(_RETRY_WAIT)
                        else:
                            self._log.error('[__getattr__] exception encountered: {0} \nstack_trace = \n{1}'.format(
                                err, traceback.format_exc()))
                            raise err
                    retries += 1
            finally:
                if _sock:
                    self._release_socket(_sock)
                del _sock
            return result

        self.__dict__[func] = func_wrapper
        return func_wrapper

    def wait(self, seconds):
        sleep(seconds)

    def _init_socket(self):
        retries = 0
        while retries < self._retries:
            try:
                _sock = self.get_socket()
                _sock.connect(self._address)
                return _sock
            except socket.timeout:
                retries -= 1
            except socket.error, err:
                if type(err.args) != tuple or err[0] != errno.ETIMEDOUT:
                    raise
                retries -= 1
            self.wait(_RETRY_WAIT)

    def _release_socket(self, sock):
        sock.close()

    def _receive_result(self, sock):
        data = sock.read()
        result, error = loads(data)
        if not error:
            return result

        self._log.error('[receive] exception encountered {0} '.format(error))
        exception = get_exception(error, self._address)
        raise exception


# ----------------------------------------------------------------------------------------------------------------------
#
# Inet backed proxy
#
# ----------------------------------------------------------------------------------------------------------------------
class InetProxy(Proxy):
    RpcSocket = InetRpcSocket


# ----------------------------------------------------------------------------------------------------------------------
#
# Gevent backed proxy
#
# ----------------------------------------------------------------------------------------------------------------------
class GeventProxy(Proxy):
    RpcSocket = GeventRpcSocket

    def wait(self, seconds):
        gevent_sleep(seconds=seconds)


# ----------------------------------------------------------------------------------------------------------------------
#
# Gevent pooled backed proxy
#
# ----------------------------------------------------------------------------------------------------------------------
class GeventPooledProxy(GeventProxy):
    def __init__(self, address, retries=2000, concurrency=32, timeout=300, **kwargs):
        super(GeventPooledProxy, self).__init__(address, sock=None, retries=retries, **kwargs)
        self._connection_pool = ConnectionPool(self.host, self.port, size=concurrency, network_timeout=timeout,
                                               connection_timeout=timeout, disable_ipv6=False)

    def _init_socket(self):
        sock = self._connection_pool.get_socket()
        return GeventRpcSocket(sock=sock)

    def _release_socket(self, sock):
        if sock:
            self._connection_pool.release_socket(sock._sock)

