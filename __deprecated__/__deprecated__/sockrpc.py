from host import Host
from msgpackutil import dumps, loads
from log import logger, LoggerMixin
from remote import current_error, get_exception
from multiprocessing import Process, cpu_count, Pipe
from multiprocessing.managers import State
from multiprocessing.util import Finalize
from geventhttpclient.connectionpool import ConnectionPool
from struct import pack, unpack, calcsize
from gevent import socket as gevent_socket, sleep as gevent_sleep
from abc import ABCMeta, abstractmethod, abstractproperty
from threading import Thread, BoundedSemaphore
from time import sleep
from gevent.monkey import patch_all
from gevent import reinit
import preforkserver
import traceback
import inspect
import errno
import socket
import sys
import signal
import psutil

__author__ = 'basca'

CONNECTION_TIMEOUT = 300
# interesting read: http://www.scarpa.name/2011/04/11/simple-rpc-python-module-part-ii/

# =================================================================================
#
# rpc methods (used by the client and the server)
#
# =================================================================================
_FORMAT = '!l'
_STARTER = '#'
_SIZE = calcsize(_FORMAT) + 1  # (the extra 1 comes from starter)
_DEFAULT_HOST = Host(name='127.0.0.1', port=0)  # port 0 means -> get a free port while binding!
_RETRIES = 2000
_RETRIES_TOUT = 2000
_RETRY_WAIT = 0.025
_SHUTDOWN_WAIT = 10.0  # 10 seconds
DEFAULT_MAX_THREADS = 1024
DEFAULT_SOCK_BACKLOG = 64

# =================================================================================
#
# Rpc Socket wrapper - abstract class - implementations follow
#
# =================================================================================
class RpcSocket(object):
    '''an rpc read / write socket wrapper'''
    __metaclass__ = ABCMeta

    def __init__(self, sock=None):
        self._sock = self._initsock(sock)

    def __getattr__(self, attr):
        if hasattr(self._sock, attr):
            return getattr(self._sock, attr)
        raise ValueError(
            '[%s], attr=%s is not a valid %s method or attribute' % (self.__class__.__name__, attr, type(self._sock)))

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
        assert isinstance(host, Host), '`host` is not an instance of Host'
        name, port = host.to_socket_tuple(proxy=False)
        self._sock.connect((name, port))
        return self

    def _sendall(self, sz_data, data):
        retries = 0
        while retries < _RETRIES_TOUT:
            self._wait_write()
            try:
                self._sock.sendall('%s%s%s' % (_STARTER, sz_data, data))
                break
            except socket.timeout:
                retries -= 1
            except socket.error, err:
                if type(err.args) != tuple \
                        or err[0] != errno.ETIMEDOUT:
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
                if type(err.args) != tuple \
                        or err[0] not in [errno.ETIMEDOUT, errno.EAGAIN]:
                    raise
                retries -= 1

    def write(self, data):
        """rpc write wrapper"""
        _len = pack(_FORMAT, len(data))
        self._sendall(_len, data)

    def read_bytes(self, size):
        """reads `size` bytes from socket, or raises an exception if not enough bytes available"""
        response = self._recv(size)
        while len(response) < size:
            chunk = self._recv(size - len(response))
            if not chunk:
                raise EOFError('[%s] socket read error expected %s bytes, received %s bytes' % (
                self.__class__.__name__, size - len(response), len(response)))
            response += chunk
        return response

    def read(self):
        """rpc read wrapper"""
        response = self.read_bytes(_SIZE)
        if response[0] != _STARTER:
            raise IOError('[%s] message delimiter is incorrect, expecting %s but found %s' % (
            self.__class__.__name__, _STARTER, response[0]))

        size = unpack(_FORMAT, response[1:])[0]
        return self.read_bytes(size)


# =================================================================================
#
# Rpc Inet Socket implementation
#
# =================================================================================
class InetRpcSocket(RpcSocket):
    def _initsock(self, sock):
        if isinstance(sock, socket.socket):
            return sock
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        return sock

    def _shutdown(self):
        self._sock.shutdown(socket.SHUT_RDWR)


# =================================================================================
#
# Rpc Gevent Socket implementation
#
# =================================================================================
class GeventRpcSocket(RpcSocket):
    def _initsock(self, sock):
        if isinstance(sock, gevent_socket.socket):
            return sock
        sock = gevent_socket.socket(gevent_socket.AF_INET, gevent_socket.SOCK_STREAM)
        return sock

    def _shutdown(self):
        self._sock.shutdown(gevent_socket.SHUT_RDWR)

    def _wait_read(self):
        gevent_socket.wait_read(self._sock.fileno(), timeout=CONNECTION_TIMEOUT.value)

    def _wait_write(self):
        gevent_socket.wait_write(self._sock.fileno(), timeout=CONNECTION_TIMEOUT.value)


# =================================================================================
#
# the rpc Gevent Proxy
#
# =================================================================================
MESSAGE = lambda msg: '#_cmd_[%s]_#' % msg


class RPCCommand(object):
    SHUTDOWN = MESSAGE('shutdown')  # shutdown the server
    PING = MESSAGE('ping')  # ping the server
    CLOSE_CONN = MESSAGE('close_conn')  # signal close connection
    INIT_ROBJ = MESSAGE('init_robj')  # signal creation of remote object on server


class BaseProxy(LoggerMixin):
    __metaclass__ = ABCMeta

    _Socket = abstractproperty()

    def __init__(self, host, retries=_RETRIES, **kwargs):
        self._host = host
        self._host_name = host.name
        self._host_port = host.port
        self._retries = retries

    port = property(fget=lambda self: self._host_port)
    name = property(fget=lambda self: self._host_name)

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
                        if err[0] == errno.ECONNRESET or \
                                        err[0] == errno.EPIPE:
                            # Connection reset by peer, or an error on the pipe...
                            self._log_message('rpc retry...')
                            if _sock:
                                self._release_socket(_sock)
                            del _sock
                            _sock = None
                            self.wait(_RETRY_WAIT)
                        else:
                            self._log_message('exception encountered: %s' % err)
                            self._log_message('stack_trace = \n%s' % traceback.format_exc())
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
        while retries < _RETRIES_TOUT:
            try:
                _sock = self._Socket()
                _sock.connect(self._host)
                return _sock
            except socket.timeout:
                retries -= 1
            except socket.error, err:
                # if type(err.args) != tuple or err[0] not in [errno.ETIMEDOUT, errno.ECONNREFUSED]:
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
    def __init__(self, host, sock, retries=_RETRIES, **kwargs):
        super(DispatcherProxy, self).__init__(host, retries=retries, **kwargs)
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
    def __init__(self, host, concurrency=32, **kwargs):
        super(GeventPooledProxy, self).__init__(host, sock=None, retries=_RETRIES, **kwargs)
        self._connection_pool = ConnectionPool(
            self._host_name, self._host_port, size=concurrency,
            network_timeout=CONNECTION_TIMEOUT.value,
            connection_timeout=CONNECTION_TIMEOUT.value,
            disable_ipv6=False)

    def _init_socket(self):
        sock = self._connection_pool.get_socket()
        return GeventRpcSocket(sock=sock)

    def _release_socket(self, sock):
        if sock:
            self._connection_pool.release_socket(sock._sock)


# =================================================================================
#
# the rpc base server (abstract)
#
# =================================================================================
class BaseRPCServer(object):
    __metaclass__ = ABCMeta

    def __init__(self, host, rpc_handler, **kwargs):
        assert isinstance(host, Host), '`host`     is not an instance of Host'
        assert rpc_handler is not None, '`rpc_handler` cannot be None'
        assert not isinstance(rpc_handler, type), '`rpc_handler` must be an instance!'
        self.rpc_handler = rpc_handler
        self._host = host
        self._host_name = host.name
        self._host_port = host.port
        methods = inspect.getmembers(self.rpc_handler, predicate=inspect.ismethod)
        self._methods = set([method_name for method_name, impl in methods if not method_name.startswith('_')])

    @abstractmethod
    def close(self):
        pass

    def stop_requests(self):
        pass

    @abstractmethod
    def run(self):
        pass

    def get_address(self, sock):
        addr, port = sock.getsockname()
        return Host(name=addr, port=port)

    address = abstractproperty()

    def shutdown(self):
        """it also exists the process it runs in!"""
        try:
            self.close()
        finally:
            sys.exit()


# =================================================================================
#
# the rpc handler mixin
#
# =================================================================================
# noinspection PyBroadException
class RpcHandlerMixin(LoggerMixin):
    def _handle_request(self, sock, shutdown, methods, rpc_handler):

        try:
            request = sock.read()
            name, args, kwargs = loads(request)

            if name == RPCCommand.PING:
                self.debug('command PING received')
                result = True
            elif name == RPCCommand.CLOSE_CONN:
                self.debug('command CLOSE_CONN received')
                result = True
            elif name == RPCCommand.SHUTDOWN:
                self.debug('command SHUTDOWN received')
                shutdown()
                result = True
            elif name not in methods:
                raise NameError('method `%s` not found in handler object' % name)
            else:
                func = getattr(rpc_handler, name)
                result = func(*args, **kwargs)
            error = None
        except Exception:
            error = current_error()
            result = None
            self.debug('[SOCKETRPC] request error! traceback: \n%s' % traceback.format_exc())
        response = dumps((result, error))
        sock.write(response)


# =================================================================================
#
# the rpc threaded server
#
# =================================================================================
class ThreadedRPCServer(BaseRPCServer, RpcHandlerMixin):
    def __init__(self, host, rpc_handler, threads=DEFAULT_MAX_THREADS, backlog=DEFAULT_SOCK_BACKLOG):
        super(ThreadedRPCServer, self).__init__(host, rpc_handler)
        self._semaphore = BoundedSemaphore(value=threads)
        self._sock = InetRpcSocket()
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # self._sock.settimeout(None)
        self._sock.setblocking(1)
        self._sock.bind((self._host.name, self._host.port))
        self._backlog = backlog
        self._address = self.get_address(self._sock)

    address = property(fget=lambda self: self._address)

    def close(self):
        self._sock.close()
        if hasattr(self.rpc_handler, 'close'):
            self.rpc_handler.close()

    def run(self):
        self.debug('starting ... ')
        try:
            self._sock.listen(self._backlog)
            while True:
                sock, addr = self._sock.accept()
                self._semaphore.acquire()
                thread = Thread(target=self.handle_request, args=(sock,))
                thread.daemon = True
                thread.start()
        finally:
            self.debug('closing the server.')
            self.close()

    def handle_request(self, sock):
        try:
            sock = InetRpcSocket(sock)
            self._handle_request(sock, self.close, self._methods, self.rpc_handler)
        except EOFError:
            self.debug('eof error on handle_request')
        finally:
            sock.close()
            self._semaphore.release()


# =================================================================================
#
# the rpc prefork server (suited for parallel work!)
#
# =================================================================================
class RpcHandlerChild(preforkserver.BaseChild, RpcHandlerMixin):
    _methods = None
    rpc_handler = None
    shutdown = None

    # def initialize(self):
    # def handle_terminate(signum, frame):
    #         logger.info('SIGTERM received for child process [%s]'%(os.getpid()))
    #         sys.exit()
    #     signal.signal(signal.SIGTERM, handle_terminate)

    def processRequest(self):
        sock = InetRpcSocket(self.conn)
        self._handle_request(sock, self.shutdown, self._methods, self.rpc_handler)


class PreforkRPCManager(preforkserver.Manager):
    def __init__(self, childClass,
                 maxServers=20,
                 minServers=5,
                 minSpareServers=2,
                 maxSpareServers=10,
                 maxRequests=0,
                 bindIp='127.0.0.1',
                 port=10000,
                 proto='tcp',
                 listen=5):
        super(PreforkRPCManager, self).__init__(childClass,
                                                maxServers=maxServers,
                                                minServers=minServers,
                                                minSpareServers=minSpareServers,
                                                maxSpareServers=maxSpareServers,
                                                maxRequests=maxRequests,
                                                bindIp=bindIp,
                                                port=port,
                                                proto=proto,
                                                listen=listen)
        # bind at init... (so we can read address from it ... )
        super(PreforkRPCManager, self).preBind()
        super(PreforkRPCManager, self)._bind()
        super(PreforkRPCManager, self).postBind()

    def _bind(self):
        # TODO: overriden so that there is no binding during call to run! (a hack until the API changes...)
        pass

    def _signalSetup(self):
        # TODO: overriden so that there is no signal setup during call to run! (a hack until the API changes...)
        pass


class PreforkedRPCServer(BaseRPCServer, LoggerMixin):
    def __init__(self, host, rpc_handler, backlog=DEFAULT_SOCK_BACKLOG,
                 maxServers=cpu_count() * 2,
                 minServers=cpu_count(),
                 minSpareServers=cpu_count(),
                 maxSpareServers=cpu_count(),
                 maxRequests=0):
        super(PreforkedRPCServer, self).__init__(host, rpc_handler)

        self._Child = RpcHandlerChild
        self._Child._methods = self._methods
        self._Child.rpc_handler = self.rpc_handler
        self._Child.shutdown = self.shutdown

        self._manager = PreforkRPCManager(self._Child,
                                          maxServers=maxServers,
                                          minServers=minServers,
                                          minSpareServers=minSpareServers,
                                          maxSpareServers=maxSpareServers,
                                          maxRequests=maxRequests,
                                          bindIp=self._host_name,
                                          port=self._host_port,
                                          proto='tcp',
                                          listen=backlog)
        self._address = self.get_address(self._manager.accSock)

    address = property(fget=lambda self: self._address)

    def close(self):
        self.info('closing ... ')
        if hasattr(self.rpc_handler, 'close'):
            self.rpc_handler.close()
        self._manager.close()
        # self.info('signaling children')
        # self.signal_children()
        self.info('exiting ... ')

    def run(self):
        self.info('starting')
        self._manager.run()


# =================================================================================
#
# the Rpc Manager - gevent friendly - similar in scope to the multiprocessing
# Manager class, however the API differs
#
# =================================================================================
class GeventManager(LoggerMixin):
    def __init__(self, handler_class, handler_args=(), handler_kwargs={},
                 host=None, logger=logger,
                 prefork=False, async=True, pooled=False, gevent_patch=False, concurrency=32, **kwargs):
        assert isinstance(handler_class, type), '`handler_class` must be a class (type)'
        if host:
            assert isinstance(host, Host), '`host` is not an instance of Host'
        self._process = None
        self._host = host if host else _DEFAULT_HOST
        self._state = State()
        self._state.value = State.INITIAL
        self._logger = logger
        self._kwargs = kwargs
        self._RpcHandler = handler_class
        self._handler_args = handler_args
        self._handler_kwargs = handler_kwargs
        self._Server = PreforkedRPCServer if prefork else ThreadedRPCServer
        self._async = async
        self._Proxy = InetProxy
        self._concurrency = concurrency
        if self._async:
            self._Proxy = GeventPooledProxy if pooled else GeventProxy
            self._gevent_patch = gevent_patch
        self._log_message('using Server = %s' % self._Server.__name__)
        self._log_message('using Proxy  = %s' % self._Proxy.__name__)

    port = property(fget=lambda self: self._host.port)
    name = property(fget=lambda self: self._host.name)

    def _run_server(self, HandlerClass, host, writer, h_args=(), h_kwargs={}, srv_kwargs={}, gevent_patch=False):
        """ Create a server, report its address and run it """
        _host = host
        try:
            if gevent_patch:
                reinit()
                patch_all()
            server = None
            rpc_handler = HandlerClass(*h_args, **h_kwargs)

            retries = 0
            while retries < _RETRIES:
                try:
                    server = self._Server(_host, rpc_handler, **srv_kwargs)
                    break
                except socket.timeout:
                    retries -= 1
                except socket.error, err:
                    if type(err.args) != tuple \
                            or err[0] not in [errno.ETIMEDOUT, errno.EAGAIN, errno.EADDRINUSE]:
                        raise
                    retries -= 1

            if server:
                writer.send(server.address)
                writer.close()
                server.run()
            else:
                writer.close()
        except Exception, err:
            self._log_message('the RPC server exited. %s' % ('Exception on exit: %s' % err if err.message else ''))


    def dispatch_command(self, command):
        proxy = InetProxy(self._host)
        return getattr(proxy, command)()

    def shutdown_server(self):
        return self.dispatch_command(RPCCommand.SHUTDOWN)

    def ping_server(self):
        return self.dispatch_command(RPCCommand.PING)

    def start(self, wait=True):
        """ start server in a different process (avoid blocking the main thread due to the servers event loop ) """
        assert self._state.value == State.INITIAL, '[rpc manager] has allready been initialized'

        reader, writer = Pipe(duplex=False)

        self._process = Process(target=self._run_server, args=(self._RpcHandler, self._host, writer),
                                kwargs={
                                    'h_args': self._handler_args,
                                    'h_kwargs': self._handler_kwargs,
                                    'srv_kwargs': self._kwargs,
                                    'gevent_patch': self._gevent_patch if self._async else False
                                })

        ident = ':'.join(str(i) for i in self._process._identity)
        self._process.name = type(self).__name__ + '-' + ident
        self._process.start()

        writer.close()
        self._host = reader.recv()
        reader.close()
        self._log_message('server starting on %s:%s' % (self._host.name, self._host.port))

        self.shutdown = Finalize(self, self._finalize, args=(), exitpriority=0)

        if wait:
            while True:
                try:
                    if self._process.is_alive():
                        self.ping_server()
                        self._log_message('server started OK')
                        self._state.value = State.STARTED
                        return True
                    else:
                        return False
                except:
                    sleep(0.01)
            return False
        return True

    def restart(self, wait=None):
        self.debug('restart')
        self.shutdown()
        self._state.value = State.INITIAL
        self.start(wait=True)
        self.debug('restarted')

    def stop(self):
        self.shutdown()

    def get_proxy(self):
        return self._Proxy(self._host, concurrency=self._concurrency)

    proxy = property(fget=get_proxy)

    def _signal_children(self):
        pid = self._process.pid
        proc = psutil.Process(pid)
        kids = proc.get_children(recursive=False)
        self.debug('signaling %s request child processes' % len(kids))
        for kid in kids:
            try:
                self.debug('\tsignal request process [%s]' % kid.pid)
                kid.send_signal(signal.SIGUSR1)
            except psutil.NoSuchProcess:
                self.error('\tprocess [%s] no longer exists (skipping)' % kid.pid)

    # noinspection PyBroadException
    def _finalize(self):
        """ Shutdown the manager process; will be registered as a finalizer """
        if not self._process:
            return

        if self._process.is_alive():
            self._signal_children()

            self.debug('sending shutdown message to server')
            try:
                self.shutdown_server()
            except Exception:
                pass

            self.debug('wait for server-starter process to terminate')
            self._process.join(timeout=_SHUTDOWN_WAIT)

            if self._process.is_alive():
                self.debug('manager still alive')
                if hasattr(self._process, 'terminate'):
                    self.debug('trying to `terminate()` manager process')
                    self._process.terminate()
                    self._process.join(timeout=_SHUTDOWN_WAIT)
                    if self._process.is_alive():
                        self.debug('manager still alive after terminate!')
            else:
                self.debug('server-starter process has terminated')
        self._state.value = State.SHUTDOWN

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()

    host = property(fget=lambda self: self._host)

