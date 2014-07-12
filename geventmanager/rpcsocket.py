from geventmanager.log import get_logger
from abc import ABCMeta, abstractmethod
from struct import pack, unpack, calcsize
from gevent import socket as gevent_socket
from time import sleep
import socket
import errno


__all__ = ['RpcSocket', 'InetRpcSocket', 'GeventRpcSocket']

__author__ = 'basca'

# ----------------------------------------------------------------------------------------------------------------------
#
# internal constants
#
# ----------------------------------------------------------------------------------------------------------------------

_FORMAT = '!l'
_STARTER = '#'
_SIZE = calcsize(_FORMAT) + 1  # (the extra 1 comes from starter)

# ----------------------------------------------------------------------------------------------------------------------
#
# an RPC socket wrapper
#
# ----------------------------------------------------------------------------------------------------------------------
def retry(max_retries, wait=None):
    def _decorator(function):
        def wrapper(*args, **kwargs):
            _retries = 0
            while _retries < max_retries:
                try:
                    return function(*args, **kwargs)
                except socket.timeout:
                    _retries -= 1
                except socket.error, err:
                    # if type(err.args) != tuple or err[0] not in [errno.ETIMEDOUT, errno.EAGAIN]:
                    # raise
                    if err[0] in [errno.ETIMEDOUT, errno.EAGAIN]:
                        _retries -= 1
                    else:
                        raise err
                if hasattr(wait, '__call__'):
                    wait()

        return wrapper

    return _decorator


class RpcSocket(object):
    __metaclass__ = ABCMeta

    public = ['port', 'host', 'address', 'close', 'connect', 'write', 'read']

    def __init__(self, sock=None, mx_retries=2000, **kwargs):
        self._sock = self._init_sock(sock)
        self._max_retries = mx_retries
        self._address = None

        self._log = get_logger(self.__class__.__name__)

        # set fast retry-enabled internal socket operations
        @retry(self._max_retries, wait=self._wait_read)
        def _retry_recv(size):
            return self._sock.recv(size)

        self.recv = _retry_recv

        @retry(self._max_retries, wait=self._wait_read)
        def _retry_sendall(sz_data, data):
            self._sock.sendall(''.join((_STARTER, sz_data, data)))

        self.sendall = _retry_sendall

        @retry(self._max_retries, wait=self._wait_read)
        def _retry_recv_into(buff, size):
            return self._sock.recv_into(buff, size)

        self.recv_into = _retry_recv_into

    def __getattr__(self, attr):
        if hasattr(self._sock, attr):
            return getattr(self._sock, attr)
        raise ValueError('[{0}], attr={1} is not a valid {2} method or attribute'.format(
            self.__class__.__name__, attr, type(self._sock)))

    @abstractmethod
    def _init_sock(self, sock):
        return sock

    @abstractmethod
    def _shutdown(self):
        return None

    @property
    def port(self):
        return self._address[1]

    @property
    def host(self):
        return self._address[0]

    @property
    def address(self):
        return self._address

    def close(self):
        if self._sock is not None:
            try:
                self._shutdown()
            except socket.error as e:
                pass
            self._sock.close()

    def _wait_read(self):
        pass

    def _wait_write(self):
        pass

    def connect(self, address):
        if isinstance(address, (tuple, list)):
            host, port = address
        elif isinstance(address, (str, unicode)):
            host, port = address.split(':')
            port = int(port)
        else:
            raise ValueError('address, must be either a tuple/list or string of the host:port form')
        self._address = (host, port)
        self._sock.connect(self._address)
        return self

    def write(self, data):
        size = pack(_FORMAT, len(data))
        self.sendall(size, data)

    def _read_bytes(self, size):
        c_size = 0
        chunks = []
        while c_size < size:
            chunk = self.recv(size - c_size)
            if not chunk:
                raise EOFError('[{0}] socket read error expected {1} bytes, received {2} bytes'.format(
                    self.__class__.__name__, size - c_size, c_size))
            chunks.append(chunk)
            c_size += len(chunk)
        return ''.join(chunks)

    def read(self):
        response = self._read_bytes(_SIZE)
        if response[0] != _STARTER:
            raise IOError('[{0}] message delimiter is incorrect, expecting {1} but found {2}'.format(
                self.__class__.__name__, _STARTER, response[0]))
        size = unpack(_FORMAT, response[1:])[0]
        return self._read_bytes(size)


# ----------------------------------------------------------------------------------------------------------------------
#
# RpcSocket backed by a blocking INET socket
#
# ----------------------------------------------------------------------------------------------------------------------
class InetRpcSocket(RpcSocket):
    def _init_sock(self, sock):
        if isinstance(sock, socket.socket):
            return sock
        return socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def _shutdown(self):
        self._sock.shutdown(socket.SHUT_RDWR)

    def _wait_read(self):
        sleep(0.01)


# ----------------------------------------------------------------------------------------------------------------------
#
# RpcSocket backed by a non-blocking Gevent socket
#
# ----------------------------------------------------------------------------------------------------------------------
class GeventRpcSocket(RpcSocket):
    def __init__(self, sock=None, connection_timeout=300):
        super(GeventRpcSocket, self).__init__(sock=sock, connection_timeout=connection_timeout)
        self.connection_timeout = connection_timeout

    def _init_sock(self, sock):
        if isinstance(sock, gevent_socket.socket):
            return sock
        return gevent_socket.socket(gevent_socket.AF_INET, gevent_socket.SOCK_STREAM)

    def _shutdown(self):
        self._sock.shutdown(gevent_socket.SHUT_RDWR)

    def _wait_read(self):
        gevent_socket.wait_read(self._sock.fileno(), timeout=self.connection_timeout)

    def _wait_write(self):
        gevent_socket.wait_write(self._sock.fileno(), timeout=self.connection_timeout)

