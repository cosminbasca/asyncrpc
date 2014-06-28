from abc import ABCMeta, abstractproperty
import socket
import errno
import traceback
from time import sleep
from gevent import sleep as gevent_sleep
from geventhttpclient.connectionpool import ConnectionPool
from msgpackutil import dumps, loads
from geventutil.rpcsocket import GeventRpcSocket, InetRpcSocket, RpcSocket
from geventutil.log import get_logger
from geventutil.exceptions import get_exception


__author__ = 'basca'

__all__ = ['Proxy', 'InetProxy', 'GeventProxy', 'GeventPooledProxy', 'Dispatcher', 'dispatch']

_RETRY_WAIT = 0.025


# ----------------------------------------------------------------------------------------------------------------------
#
# base Rpc proxy
#
# ----------------------------------------------------------------------------------------------------------------------
class Proxy(object):
    __metaclass__ = ABCMeta

    public = ['port', 'host', 'address', 'send', 'wait']

    @abstractproperty
    def _rpc_socket_impl(self):
        return None

    def get_socket(self):
        sock = self._rpc_socket_impl()
        if not isinstance(sock, RpcSocket):
            raise ValueError('socket is not an RpcSocket instance!')
        return sock

    def __init__(self, instance_id, address, slots=None, retries=2000, **kwargs):
        if isinstance(address, (tuple, list)):
            host, port = address
        elif isinstance(address, (str, unicode)):
            host, port = address.split(':')
            port = int(port)
        else:
            raise ValueError(
                'address, must be either a tuple/list or string of the name:port form, got {0}'.format(address))
        self._id = instance_id
        self._address = (host, port)
        self._retries = retries
        self._slots = slots
        self._log = get_logger(self.__class__.__name__)

    def __del__(self):
        # delete server-side instance
        self.send('#DEL')

    @property
    def port(self):
        return self._address[1]

    @property
    def host(self):
        return self._address[0]

    @property
    def address(self):
        return self._address

    def send(self, name, *args, **kwargs):
        _sock = None
        result = None
        try:
            retries = 0
            while retries < self._retries:
                # wait until a connection becomes available
                try:
                    _sock = self._init_socket()
                    _sock.setblocking(1)
                    _sock.write(dumps((name, self._id, args, kwargs)))

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

    def __getattr__(self, func):
        def func_wrapper(*args, **kwargs):
            if self._slots and func not in self._slots:
                raise ValueError('access to function {0} is restricted'.format(func))
            return self.send(func, *args, **kwargs)

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
    @property
    def _rpc_socket_impl(self):
        return InetRpcSocket


# ----------------------------------------------------------------------------------------------------------------------
#
# Gevent backed proxy
#
# ----------------------------------------------------------------------------------------------------------------------
class GeventProxy(Proxy):
    @property
    def _rpc_socket_impl(self):
        return GeventRpcSocket

    def wait(self, seconds):
        gevent_sleep(seconds=seconds)


# ----------------------------------------------------------------------------------------------------------------------
#
# Gevent pooled backed proxy
#
# ----------------------------------------------------------------------------------------------------------------------
class GeventPooledProxy(GeventProxy):
    def __init__(self, instance_id, address, slots=None, retries=2000, concurrency=32, timeout=300, **kwargs):
        super(GeventPooledProxy, self).__init__(instance_id, address, slots=slots, sock=None, retries=retries, **kwargs)
        self._connection_pool = ConnectionPool(self.host, self.port, size=concurrency, network_timeout=timeout,
                                               connection_timeout=timeout, disable_ipv6=False)

    def _init_socket(self):
        sock = self._connection_pool.get_socket()
        return GeventRpcSocket(sock=sock)

    def _release_socket(self, sock):
        if sock:
            self._connection_pool.release_socket(sock._sock)


# ----------------------------------------------------------------------------------------------------------------------
#
# dispatcher object
#
# ----------------------------------------------------------------------------------------------------------------------
class Dispatcher(InetProxy):
    public = ['port', 'host', 'address']

    def __init__(self, address, type_id=None, **kwargs):
        super(Dispatcher, self).__init__(type_id, address.address if isinstance(address, RpcSocket) else address,
                                         **kwargs)

    def __call__(self, message, *args, **kwargs):
        if not message.startswith('#'):
            raise ValueError('method "dispatch" can only be used to serve builtin messages!')
        return self.send(message, *args, **kwargs)

    def __del__(self):
        pass  # override so that no deletion occurs on server side ...


def dispatch(address, message, *args, **kwargs):
    return Dispatcher(address)(message, *args, **kwargs)