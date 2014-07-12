from geventmanager.rpcsocket import GeventRpcSocket, InetRpcSocket, RpcSocket, RETRY_WAIT, retry
from geventmanager.exceptions import get_exception
from geventmanager.log import get_logger
from geventhttpclient.connectionpool import ConnectionPool
from abc import ABCMeta, abstractproperty
from gevent import sleep as gevent_sleep
from msgpackutil import dumps, loads
from time import sleep
import traceback
import socket
import errno


__author__ = 'basca'

__all__ = ['Proxy', 'InetProxy', 'GeventProxy', 'GeventPooledProxy', 'Dispatcher', 'dispatch']

RETRIES_CONN, RETRIES_WRITE = 0, 0

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
        self._RpcSocketClass = self._rpc_socket_impl
        if not issubclass(self._RpcSocketClass, RpcSocket):
            raise ValueError('SocketClass of type {0} is not an RpcSocket subclass'.format(self._RpcSocketClass))

        @retry(self._retries, wait=self.wait)
        def connect():
            return self._init_socket()
        self._connect = connect

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
                connected = False
                try:
                    _sock = self._connect()
                    connected = True
                    # _sock.setblocking(1)
                    _sock.write(dumps((name, self._id, args, kwargs)))

                    result = self._receive_result(_sock)
                    break
                except socket.error, err:
                    if err[0] == errno.ECONNRESET or err[0] == errno.EPIPE:
                        self._log.info('rpc retry (due to: {0}) '.format(err))
                        if _sock:
                            self._release_socket(_sock)
                        del _sock
                        _sock = None
                        self.wait()
                        global RETRIES_CONN, RETRIES_WRITE
                        if connected:
                            RETRIES_WRITE += 1
                        else:
                            RETRIES_CONN += 1
                        print 'CONN RETRIES = {0}, WRITE RETRIES = {1}'.format(RETRIES_CONN, RETRIES_WRITE)
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
        func_wrapper.__name__ = func
        self.__dict__[func] = func_wrapper
        return func_wrapper

    def wait(self, seconds=RETRY_WAIT):
        sleep(seconds)

    def _init_socket(self):
        sock = self._RpcSocketClass()
        sock.connect(self._address)
        return sock

    def _release_socket(self, sock):
        sock.close()

    def _receive_result(self, sock):
        data = sock.read()
        result, error = loads(data)
        if not error:
            return result

        self._log.error('[receive] exception encountered {0} '.format(error))
        print error
        raise get_exception(error, self._address)

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

    def wait(self, seconds=RETRY_WAIT):
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