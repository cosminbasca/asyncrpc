from abc import ABCMeta, abstractmethod
import inspect
import socket
import sys
import os
import traceback
from msgpackutil import dumps, loads
from geventmanager.exceptions import current_error, InvalidInstanceId, InvalidType
from geventmanager.log import get_logger
from geventmanager.rpcsocket import InetRpcSocket, GeventRpcSocket, RpcSocket
from threading import Thread, BoundedSemaphore, RLock
import preforkserver as pfs
from multiprocessing import cpu_count

__author__ = 'basca'

__all__ = ['RpcServer', 'ThreadedRpcServer', 'PreforkedRpcServer']

# ----------------------------------------------------------------------------------------------------------------------
#
# base Rpc server api
#
# ----------------------------------------------------------------------------------------------------------------------
def get_methods(obj):
    methods = inspect.getmembers(obj, predicate=inspect.ismethod)
    return {method_name: impl for method_name, impl in methods if
            not method_name.startswith('_') and hasattr(impl, '__call__')}


class RpcServer(object):
    __metaclass__ = ABCMeta

    def __init__(self, address, registry, **kwargs):
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
        self._instances = dict()
        self._address = (host, port)
        self._mutex = RLock()

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

    @abstractmethod
    def close(self):
        pass

    def stop_requests(self):
        pass

    @abstractmethod
    def run(self):
        pass

    def shutdown(self, os_exit=True):
        try:
            self.close()
        finally:
            if os_exit:
                os._exit(0)
            else:
                sys.exit(0)

    # noinspection PyBroadException
    def _receive(self, sock):
        try:
            request = sock.read()
            name, _id, args, kwargs = loads(request)
            result = False

            if name == '#INIT':
                try:
                    self._log.debug('=> INIT')
                    self._mutex.acquire()
                    _class = self._registry[_id]
                    instance = _class(*args, **kwargs)
                    self._instances[_id] = instance, get_methods(instance)
                    result = hash(instance)
                finally:
                    self._mutex.release()
            elif name == '#DEL':
                self._log.debug('=> DEL')
                del self._instances[_id]
                result = True
            elif name == "#PING":
                self._log.debug('=> PING')
                result = True
            elif name == '#SHUTDOWN':
                self._log.debug('=> SHUTDOWN')
                self.shutdown()
                result = True
            else:
                instance_info = self._instances.get(_id, None)
                if not instance_info:
                    raise InvalidInstanceId('insance with id:{0} not registered'.format(_id))
                instance, methods = instance_info
                func = methods.get(name, None)
                if not func:
                    raise NameError('instance does not have method "{0}"'.format(name))
                result = func(*args, **kwargs)
            error = None
        except Exception:
            error = current_error()
            result = None
            self._log.error('[_handle_request] error, traceback: \n{0}'.format(traceback.format_exc()))
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
        self._semaphore = BoundedSemaphore(value=threads) # to limit the number of concurrent threads ...
        self._sock = InetRpcSocket()
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # self._sock.settimeout(None)
        self._sock.setblocking(1)
        self._sock.bind(self._address)
        self._backlog = backlog

    def close(self):
        self._sock.close()

    def run(self):
        self._log.debug('starting server ... ')
        try:
            self._sock.listen(self._backlog)
            while True:
                sock, bound_address = self._sock.accept()
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
            self._receive(sock)
        except EOFError:
            self._log.debug('eof error on handle_request')
        finally:
            sock.close()
            self._semaphore.release()


# ----------------------------------------------------------------------------------------------------------------------
#
# preforked RPC Server (backed by Inet sockets)
#
# ----------------------------------------------------------------------------------------------------------------------
class RpcHandlerChild(pfs.BaseChild):
    def __init__(self, server_socket, max_requests, child_conn, protocol, *args, **kwargs):
        self._handle_rpc = None
        super(RpcHandlerChild, self).__init__(server_socket, max_requests, child_conn, protocol, *args, **kwargs)

    def initialize(self, rpc_handler=None):
        if not hasattr(rpc_handler, 'handle_rpc'):
            raise ValueError('handler must expose handle_rpc member!')
        self._handle_rpc = getattr(rpc_handler, 'handle_rpc')
        if not hasattr(self._handle_rpc, '__call__'):
            raise ValueError('handle_rpc member is not callable')

    def process_request(self):
        sock = InetRpcSocket(self.conn)
        self._handle_rpc(sock)


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

    def run(self):
        self._log.info('starting ... ')
        self._manager.run()
