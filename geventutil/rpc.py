from abc import ABCMeta, abstractmethod
from struct import pack, unpack, calcsize
from gevent import socket as gevent_socket
import socket
import errno

__all__ = ['RpcSocket', 'InetRpcSocket', 'GeventRpcSocket', 'DEFAULT_CONNECTION_TIMEOUT']

__author__ = 'basca'

# ----------------------------------------------------------------------------------------------------------------------
#
# internal constants
#
# ----------------------------------------------------------------------------------------------------------------------

_FORMAT = '!l'
_STARTER = '#'
_SIZE = calcsize(_FORMAT) + 1  # (the extra 1 comes from starter)
_DEFAULT_HOST = ('127.0.0.1', 0)  # port 0 means -> get a free port while binding!
_RETRIES_TOUT = 2000

DEFAULT_CONNECTION_TIMEOUT = 300

# ----------------------------------------------------------------------------------------------------------------------
#
# an RPC socket wrapper
#
# ----------------------------------------------------------------------------------------------------------------------
class RpcSocket(object):
    __metaclass__ = ABCMeta

    def __init__(self, sock=None, **kwargs):
        self._sock = self._initsock(sock)

    def __getattr__(self, attr):
        if hasattr(self._sock, attr):
            return getattr(self._sock, attr)
        raise ValueError('[{0}], attr={1} is not a valid {2} method or attribute'.format(
            self.__class__.__name__, attr, type(self._sock)))

    @abstractmethod
    def _initsock(self, sock):
        return None

    @abstractmethod
    def _shutdown(self):
        return None

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

    def connect(self, host):
        if isinstance(host, (tuple, list)):
            name, port = host
        elif isinstance(host, (str, unicode)):
            name, port = host.split(':')
            port = int(port)
        else:
            raise ValueError('host, must be either a tuple/list or string of the name:port form')
        self._sock.connect((name, port))
        return self

    def _sendall(self, sz_data, data):
        retries = 0
        while retries < _RETRIES_TOUT:
            self._wait_write()
            try:
                self._sock.sendall(''.join((_STARTER, sz_data, data)))
                break
            except socket.timeout:
                retries -= 1
            except socket.error, err:
                if type(err.args) != tuple or err[0] != errno.ETIMEDOUT:
                    raise
                retries -= 1

    def _recv(self, size):
        retries = 0
        while retries < _RETRIES_TOUT:
            self._wait_read()
            try:
                return self._sock.recv(size)
            except socket.timeout:
                retries -= 1
            except socket.error, err:
                if type(err.args) != tuple or err[0] not in [errno.ETIMEDOUT, errno.EAGAIN]:
                    raise
                retries -= 1

    def write(self, data):
        _len = pack(_FORMAT, len(data))
        self._sendall(_len, data)

    def read_bytes(self, size):
        response = self._recv(size)
        while len(response) < size:
            chunk = self._recv(size - len(response))
            if not chunk:
                raise EOFError('[{0}] socket read error expected {1} bytes, received {2} bytes'.format(
                    self.__class__.__name__, size - len(response), len(response)))
            response += chunk
        return response

    def read(self):
        response = self.read_bytes(_SIZE)
        if response[0] != _STARTER:
            raise IOError('[{0}] message delimiter is incorrect, expecting {1} but found {2}'.format(
                self.__class__.__name__, _STARTER, response[0]))
        size = unpack(_FORMAT, response[1:])[0]
        return self.read_bytes(size)


# ----------------------------------------------------------------------------------------------------------------------
#
# RpcSocket backed by a blocking INET socket
#
# ----------------------------------------------------------------------------------------------------------------------
class InetRpcSocket(RpcSocket):
    def _initsock(self, sock):
        if isinstance(sock, socket.socket):
            return sock
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        return sock

    def _shutdown(self):
        self._sock.shutdown(socket.SHUT_RDWR)


# ----------------------------------------------------------------------------------------------------------------------
#
# RpcSocket backed by a non-blocking Gevent socket
#
# ----------------------------------------------------------------------------------------------------------------------
class GeventRpcSocket(RpcSocket):
    def __init__(self, sock=None, connection_timeout=DEFAULT_CONNECTION_TIMEOUT):
        super(GeventRpcSocket, self).__init__(sock=sock, connection_timeout=connection_timeout)
        self.connection_timeout = connection_timeout

    def _initsock(self, sock):
        if isinstance(sock, gevent_socket.socket):
            return sock
        return gevent_socket.socket(gevent_socket.AF_INET, gevent_socket.SOCK_STREAM)

    def _shutdown(self):
        self._sock.shutdown(gevent_socket.SHUT_RDWR)

    def _wait_read(self):
        gevent_socket.wait_read(self._sock.fileno(), timeout=self.connection_timeout)

    def _wait_write(self):
        gevent_socket.wait_write(self._sock.fileno(), timeout=self.connection_timeout)

