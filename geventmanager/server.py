from abc import ABCMeta, abstractmethod
import inspect
import socket
import sys
import os
import traceback
from msgpackutil import dumps, loads
from geventmanager.exceptions import current_error
from geventmanager.log import get_logger
from geventmanager.rpcsocket import InetRpcSocket, GeventRpcSocket, RpcSocket
from threading import Thread, BoundedSemaphore
import preforkserver as pfs
from multiprocessing import cpu_count

__author__ = 'basca'



# ----------------------------------------------------------------------------------------------------------------------
#
# base Rpc server api
#
# ----------------------------------------------------------------------------------------------------------------------
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
        self._objects = dict()
        self._address = (host, port)

        self._log = get_logger(self.__class__.__name__)

    @classmethod
    def get_methods(cls, obj):
        methods = inspect.getmembers(obj, predicate=inspect.ismethod)
        return {method_name: impl for method_name, impl in methods if
                not method_name.startswith('_') and hasattr(impl, '__call__')}

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
    def handle_rpc(self, sock):
        try:
            request = sock.read()
            oid, name, args, kwargs = loads(request)

            if name == "#PING":
                self._log.debug('=> PING')
                result = True
            elif name == "#CLOSECONN":
                self._log.debug('=> CLOSE_CONN')
                result = True
            elif name == "#SHUTDOWN":
                self._log.debug('=> SHUTDOWN')
                self.shutdown()
                result = True
            else:
                obj, methods = self._objects.get(oid, (None, None))
                if not methods:
                    _init, _args, _kwargs = self._registry[oid]
                    obj = _init(*_args, **_kwargs)
                    methods = self.get_methods(obj)
                    self._objects[oid] = obj, methods

                func = methods.get(name, None)
                if not func:
                    raise NameError('method "{0}" not found in handler object'.format(name))
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

    address = property(fget=lambda self: self._address)

    def close(self):
        self._sock.close()
        #TODO: consider other cleanup (of objects in the registry)

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
            self.handle_rpc(sock)
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
    _methods = None
    rpc_handler = None
    shutdown = None

    # def initialize(self):
    # def handle_terminate(signum, frame):
    # logger.info('SIGTERM received for child process [%s]'%(os.getpid()))
    # sys.exit()
    # signal.signal(signal.SIGTERM, handle_terminate)

    def process_request(self):
        sock = InetRpcSocket(self.conn)
        self._handle_request(sock, self.shutdown, self._methods, self.rpc_handler)


class PreforkedRpcServer(RpcServer):
    def __init__(self, host, rpc_handler, backlog=64, max_servers=cpu_count() * 2, min_servers=cpu_count(),
                 min_spare_servers=cpu_count(), max_spare_servers=cpu_count(), max_requests=0):
        super(PreforkedRpcServer, self).__init__(host, rpc_handler)

        self._Child = None
        self._Child._methods = self._methods
        self._Child.rpc_handler = self.rpc_handler
        self._Child.shutdown = self.shutdown

        RequestHandler = type('', (pfs.BaseChild,), {
            'process_request': None})

        self._manager = pfs.Manager(self._Child, max_servers=max_servers, min_servers=min_servers,
                                    min_spare_servers=min_spare_servers, max_spare_servers=max_spare_servers,
                                    max_requests=max_requests, bind_ip=self.host, port=self.port, protocol='tcp',
                                    listen=backlog)

    @property
    def bound_address(self):
        return self._manager.bound_address

    def close(self):
        self._log.info('closing ... ')
        if hasattr(self.rpc_handler, 'close'):
            self.rpc_handler.close()
        self._manager.close()
        # self.info('signaling children')
        # self.signal_children()
        self._log.info('exit')

    def run(self):
        self._log.info('starting ... ')
        self._manager.run()
