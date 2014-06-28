from abc import ABCMeta, abstractmethod, abstractproperty
from geventmanager import Dispatcher
from geventmanager.exceptions import current_error, InvalidInstanceId, InvalidStateException
from geventmanager.log import get_logger
from geventmanager.rpcsocket import InetRpcSocket, GeventRpcSocket, RpcSocket
from multiprocessing.managers import State
from multiprocessing.util import Finalize
from multiprocessing import cpu_count, Pipe, Process
from msgpackutil import dumps, loads
from threading import Thread, BoundedSemaphore, RLock
from gevent.monkey import patch_all
import preforkserver as pfs
from gevent import reinit
from pprint import pformat
from time import sleep
import traceback
import inspect
import socket
import psutil
import signal
import errno
import sys
import os

__author__ = 'basca'

__all__ = ['RpcHandler', 'RpcServer', 'ThreadedRpcServer', 'PreforkedRpcServer', 'BackgroundServerRunner']

logger = get_logger(__name__)

# ----------------------------------------------------------------------------------------------------------------------
#
# base Rpc server api
#
# ----------------------------------------------------------------------------------------------------------------------
def get_methods(obj):
    methods = inspect.getmembers(obj, predicate=inspect.ismethod)
    return {method_name: impl for method_name, impl in methods if
            not method_name.startswith('_') and hasattr(impl, '__call__')}


def dict_to_str(dictionary):
    return '\n'.join([
        '[{0}]\t{1} => {2}'.format(i, k, pformat(v))
        for i, (k, v) in enumerate(dictionary.items())
    ])


# ----------------------------------------------------------------------------------------------------------------------
#
# base Rpc server handler class
#
# ----------------------------------------------------------------------------------------------------------------------
class RpcHandler(object):
    __metaclass__ = ABCMeta

    @abstractmethod
    def receive(self, sock):
        pass

# ----------------------------------------------------------------------------------------------------------------------
#
# the actual rpc sever base api
#
# ----------------------------------------------------------------------------------------------------------------------
class RpcServer(RpcHandler):
    __metaclass__ = ABCMeta

    public = ['port', 'host', 'address', 'close', 'bound_address', 'run', 'shutdown', 'receive']

    def __init__(self, address, registry, **kwargs):
        super(RpcServer, self).__init__()

        if isinstance(address, (tuple, list)):
            host, port = address
        elif isinstance(address, (str, unicode)):
            host, port = address.split(':')
            port = int(port)
        else:
            raise ValueError('address, must be either a tuple/list or string of the name:port form')

        if not isinstance(registry, dict):
            raise ValueError('registry must be a dictionary')

        self._registry = registry
        self._address = (host, port)
        self._mutex = RLock()

        self._log = get_logger(self.__class__.__name__)

        self._handlers = {
            '#INIT': self._handler_init,
            '#DEL': self._handler_del,
            '#PING': self._handler_ping,
            '#SHUTDOWN': self._handler_shutdown,
            '#DEBUG': self._handler_debug,
        }

    def _get_handler(self, name):
        return self._handlers.get(name, None)

    @property
    def port(self):
        return self._address[1]

    @property
    def host(self):
        return self._address[0]

    @property
    def address(self):
        return self._address

    @abstractmethod
    def close(self):
        pass

    @abstractproperty
    def bound_address(self):
        pass

    @abstractmethod
    def start(self):
        pass

    def shutdown(self, os_exit=True):
        try:
            self.close()
        finally:
            if os_exit:
                os._exit(0)
            else:
                sys.exit(0)

    def _handler_init(self, name, type_id, *args, **kwargs):
        try:
            self._mutex.acquire()
            _class = self._registry[type_id]
            instance = _class(*args, **kwargs)
            instance_id = hash(instance)
            self._registry[instance_id] = instance
            self._log.debug('got instance id:{0}'.format(instance_id))
            return instance_id
        finally:
            self._mutex.release()

    def _handler_del(self, name, instance_id, *args, **kwargs):
        del self._registry[instance_id]
        return True

    def _handler_ping(self, name, instance_id, *args, **kwargs):
        return True

    def _handler_shutdown(self, name, instance_id, *args, **kwargs):
        self.shutdown()
        return True

    def _handler_debug(self, name, instance_id, *args, **kwargs):
        self._log.info('''
------------------------------------------------------------------------------------------------------------------------
REGISTRY:
{0}
------------------------------------------------------------------------------------------------------------------------
'''.format(dict_to_str(self._registry)))

    def _handle_rpc_call(self, name, instance_id, *args, **kwargs):
        instance = self._registry.get(instance_id, None)
        if not instance:
            raise InvalidInstanceId('insance with id:{0} not registered'.format(instance_id))
        func = getattr(instance, name, None)
        if not func:
            raise NameError('instance does not have method "{0}"'.format(name))
        return func(*args, **kwargs)

    def receive(self, sock):
        try:
            request = sock.read()
            name, _id, args, kwargs = loads(request)

            handler = self._handlers.get(name, None)
            if not hasattr(handler, '__call__'):
                handler = self._handle_rpc_call
                self._log.debug('calling function: "{0}"'.format(name))
            else:
                self._log.info('received: "{0}"'.format(name))
            result = handler(name, _id, *args, **kwargs)
            error = None
        except Exception, e:
            error = current_error()
            result = None
            self._log.error('[_handle_request] error: {0}, traceback: \n{1}'.format(e, traceback.format_exc()))
        response = dumps((result, error))
        sock.write(response)
# ----------------------------------------------------------------------------------------------------------------------
#
# Threaded RPC server - backed by an INET socket
#
# ----------------------------------------------------------------------------------------------------------------------
class ThreadedRpcServer(RpcServer):
    def __init__(self, address, registry, threads=1024, backlog=64):
        super(ThreadedRpcServer, self).__init__(address, registry)
        self._semaphore = BoundedSemaphore(value=threads)  # to limit the number of concurrent threads ...
        self._sock = InetRpcSocket()
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # self._sock.settimeout(None)
        self._sock.setblocking(1)
        self._sock.bind(self._address)
        self._backlog = backlog
        self._bound_address = self._sock.getsockname()

    def close(self):
        self._sock.close()

    def start(self):
        self._log.debug('starting server ... ')
        try:
            self._sock.listen(self._backlog)
            while True:
                sock, addr = self._sock.accept()
                self._semaphore.acquire()
                thread = Thread(target=self.handle_request, args=(sock,))
                thread.daemon = True
                thread.start()
        finally:
            self._log.debug('closing the server ...')
            self.close()
            self._log.debug('server shutdown complete')

    def handle_request(self, sock):
        try:
            sock = InetRpcSocket(sock)
            self.receive(sock)
        except EOFError:
            self._log.debug('eof error on handle_request')
        finally:
            sock.close()
            self._semaphore.release()

    @property
    def bound_address(self):
        return self._bound_address


# ----------------------------------------------------------------------------------------------------------------------
#
# preforked RPC Server (backed by Inet sockets)
#
# ----------------------------------------------------------------------------------------------------------------------
class RpcHandlerChild(pfs.BaseChild):
    def __init__(self, server_socket, max_requests, child_conn, protocol, rpc_handler=None):
        super(RpcHandlerChild, self).__init__(server_socket, max_requests, child_conn, protocol,
                                              rpc_handler=rpc_handler)

        if not isinstance(rpc_handler, RpcHandler):
            raise ValueError('rpc_handler is not an instance of RpcHandler')
        self.receive = rpc_handler.receive

    def process_request(self):
        sock = InetRpcSocket(self.conn)
        self.receive(sock)


class PreforkedRpcServer(RpcServer):
    def __init__(self, host, registry, backlog=64, max_servers=cpu_count() * 2, min_servers=cpu_count(),
                 min_spare_servers=cpu_count(), max_spare_servers=cpu_count(), max_requests=0):
        super(PreforkedRpcServer, self).__init__(host, registry)
        self._manager = pfs.Manager(RpcHandlerChild, child_kwargs={'rpc_handler': self},
                                    max_servers=max_servers, min_servers=min_servers,
                                    min_spare_servers=min_spare_servers, max_spare_servers=max_spare_servers,
                                    max_requests=max_requests, bind_ip=self.host, port=self.port, protocol='tcp',
                                    listen=backlog)

    @property
    def bound_address(self):
        return self._manager.bound_address

    def close(self):
        self._log.info('closing ... ')
        self._manager.close()
        self._log.info('exit')

    def start(self):
        self._log.info('starting ... ')
        self._manager.run()


# ----------------------------------------------------------------------------------------------------------------------
#
# Background rpc server runner
#
# ----------------------------------------------------------------------------------------------------------------------
class BackgroundServerRunner(object):
    public = ['start', 'stop', 'restart', 'bound_address', 'dispatch', 'is_running']

    def __init__(self, server_class=ThreadedRpcServer, address=('127.0.0.1', 0), registry=None, gevent_patch=False,
                 retries=2000):
        if not issubclass(server_class, RpcServer):
            raise ValueError('server_class must be a subclass of RpcServer')
        self._server_class = server_class
        self._address = address if address else ('127.0.0.1', 0)
        self._registry = registry

        self._gevent_patch = gevent_patch
        self._retries = retries
        self._state = State()
        self._state.value = State.INITIAL
        self._process = None
        self._bound_address = None
        self._dispatch = None

        self._stop = lambda: None

        self._log = get_logger(server_class.__name__)

    def _background_start(self, writer, **kwargs):
        try:
            if self._gevent_patch:
                reinit()
                patch_all()
            server = None

            retries = 0
            while retries < self._retries:
                try:
                    server = self._server_class(self._address, self._registry, **kwargs)
                    break
                except socket.timeout:
                    retries -= 1
                except socket.error, err:
                    if type(err.args) != tuple or err[0] not in [errno.ETIMEDOUT, errno.EAGAIN, errno.EADDRINUSE]:
                        raise
                    retries -= 1

            if server:
                writer.send(server.bound_address)
                writer.close()
                server.start()
            else:
                writer.close()
        except Exception, err:
            self._log.error(
                'Rpc server exited. {0}'.format('Exception on exit: {0}'.format(err if err.message else '')))


    def start(self, wait=True):
        if self._state.value != State.INITIAL:
            raise InvalidStateException('[rpc manager] has already been initialized')

        reader, writer = Pipe(duplex=False)

        self._process = Process(target=self._background_start, args=(writer,))
        self._process.name = type(self).__name__ + '-' + self._process.name
        self._log.debug('starting background process: {0}'.format(self._process.name))
        self._process.start()

        writer.close()
        self._bound_address = reader.recv()
        reader.close()
        self._log.debug('server starting on {0}'.format(self._bound_address))
        self._dispatch = Dispatcher(self._bound_address)
        self._log.debug('server initialized dispatcher')

        self._stop = Finalize(self, self._finalize, args=(), exitpriority=0)

        if wait:
            while True:
                try:
                    if self._process.is_alive():
                        self._log.debug("server process started, waiting for initialization ... ")
                        self._dispatch("#PING")
                        self._state.value = State.STARTED
                        self._log.debug('server started OK')
                        return True
                    else:
                        return False
                except Exception, e:
                    self._log.error("error: {0}".format(e))
                    sleep(0.01)
            return False
        return True

    def restart(self, wait=None):
        self._log.debug('restart')
        self._stop()
        self._state.value = State.INITIAL
        self.start(wait=wait)
        self._log.debug('restarted')

    def stop(self):
        self._stop()

    def _signal_children(self, signals=(signal.SIGINT, signal.SIGUSR1)):
        pid = self._process.pid
        proc = psutil.Process(pid)
        kids = proc.get_children(recursive=False)
        if len(kids):
            self._log.debug('signaling {0} request child processes'.format(len(kids)))
            for kid in kids:
                try:
                    self._log.debug('\t signal request process [{0}]'.format(kid.pid))
                    for sig in signals:
                        kid.send_signal(sig)
                except psutil.NoSuchProcess:
                    self._log.error('\t process [{0}] no longer exists (skipping)'.format(kid.pid))
        else:
            self._log.debug('no child processes to signal on stop')

    # noinspection PyBroadException
    def _finalize(self):
        if not self._process:
            return

        if self._process.is_alive():
            self._signal_children()

            self._log.debug('sending shutdown message to server')
            try:
                self._dispatch("#SHUTDOWN")
            except Exception:
                pass

            self._log.debug('wait for server-starter process to terminate')
            self._process.join(timeout=10.0)

            if self._process.is_alive():
                self._log.debug('manager still alive')
                if hasattr(self._process, 'terminate'):
                    self._log.debug('trying to `terminate()` manager process')
                    self._process.terminate()
                    self._process.join(timeout=10.0)
                    if self._process.is_alive():
                        self._log.debug('manager still alive after terminate!')
            else:
                self._log.debug('server-starter process has terminated')
        self._state.value = State.SHUTDOWN

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._stop()

    @property
    def bound_address(self):
        return self._bound_address

    @property
    def dispatch(self):
        return self._dispatch

    @property
    def is_running(self):
        return self._state.value == State.STARTED