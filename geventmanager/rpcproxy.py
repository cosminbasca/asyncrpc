from abc import ABCMeta, abstractproperty
import socket
import errno
import traceback
from gevent import sleep as gevent_sleep
from time import sleep

__author__ = 'basca'


def _command(name):
    return '#cmd:{0}#'.format(name)


_CMD_SHUTDOWN = _command('shutdown')
_CMD_PING = _command('ping')
_CMD_CLOSE_CONN = _command('close_conn')
_INIT_ROBJ = _command('init_robj')

_RETRY_WAIT = 0.025


class BaseProxy(object):
    __metaclass__ = ABCMeta

    _Socket = abstractproperty()

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
                        self._call_method(func, _sock, *args, **kwargs)
                        result = self._receive_result(_sock)
                        break
                    except socket.error, err:
                        if err[0] == errno.ECONNRESET or err[0] == errno.EPIPE:
                            # Connection reset by peer, or an error on the pipe...
                            self._log_message('rpc retry...') # TODO: handle the logging ...
                            if _sock:
                                self._release_socket(_sock)
                            del _sock
                            _sock = None
                            self.wait(_RETRY_WAIT)
                        else:
                            self._log_message('exception encountered: {0}'.format(err))
                            self._log_message('stack_trace = \n{0}'.format(traceback.format_exc()))
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
                _sock = self._Socket()
                _sock.connect(self._host)
                return _sock
            except socket.timeout:
                retries -= 1
            except socket.error, err:
                if type(err.args) != tuple or err[0] != errno.ETIMEDOUT:
                    raise
                retries -= 1
            self.wait(0.05)

    def _release_socket(self, sock):
        sock.close()

    def _call_method(self, func, sock, *args, **kwargs):
        request = dumps((func, args, kwargs))
        sock.write(request)

    def _receive_result(self, sock):
        data = sock.read()
        result, error = loads(data)
        if not error:
            return result

        self.info('[ >>>> SCOKET RPC CLIENT <<<< ] ERROR = %s ' % error)
        exception = get_exception(error, self._host)
        # self.debug('[SOCKETRPC CLIENT] got exception = %s, %s'%(type(exception), exception))
        raise exception


# =================================================================================
#
# the rpc Proxy classes
#
# =================================================================================
class DispatcherProxy(BaseProxy):
    def __init__(self, address, sock, retries=_RETRIES, **kwargs):
        super(DispatcherProxy, self).__init__(address, retries=retries, **kwargs)
        self._sock = sock

    def _init_socket(self):
        return self._sock

    def _release_socket(self, sock):
        sock.close()


# ---------------------------------------------------------------------------------
class InetProxy(BaseProxy):
    _Socket = InetRpcSocket


# ---------------------------------------------------------------------------------
class GeventProxy(BaseProxy):
    _Socket = GeventRpcSocket

    def wait(self, seconds):
        gevent_sleep(seconds=seconds)


# ---------------------------------------------------------------------------------
class GeventPooledProxy(GeventProxy):
    def __init__(self, address, concurrency=32, **kwargs):
        super(GeventPooledProxy, self).__init__(address, sock=None, retries=_RETRIES, **kwargs)
        self._connection_pool = ConnectionPool(
            self._host, self._port, size=concurrency,
            network_timeout=CONNECTION_TIMEOUT.value,
            connection_timeout=CONNECTION_TIMEOUT.value,
            disable_ipv6=False)

    def _init_socket(self):
        sock = self._connection_pool.get_socket()
        return GeventRpcSocket(sock=sock)

    def _release_socket(self, sock):
        if sock:
            self._connection_pool.release_socket(sock._sock)

