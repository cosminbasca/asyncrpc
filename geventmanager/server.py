from abc import ABCMeta, abstractmethod, abstractproperty
import inspect
from pprint import pformat
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
from multiprocessing import cpu_count, Manager

__author__ = 'basca'

__all__ = ['RpcHandler', 'RpcServer', 'ThreadedRpcServer', 'PreforkedRpcServer']

# ----------------------------------------------------------------------------------------------------------------------
#
# base Rpc server api
#
# ----------------------------------------------------------------------------------------------------------------------
def get_methods(obj):
    methods = inspect.getmembers(obj, predicate=inspect.ismethod)
    return {method_name: impl for method_name, impl in methods if
            not method_name.startswith('_') and hasattr(impl, '__call__')}


class RpcHandler(object):
    __metaclass__ = ABCMeta

    @abstractmethod
    def receive(self, sock):
        pass


class RpcServer(RpcHandler):
    __metaclass__ = ABCMeta

    public = ['port', 'host', 'address', 'close', 'bound_address', 'run', 'shutdown', 'receive']

    def __init__(self, address, registry, **kwargs):
        if isinstance(address, (tuple, list)):
            host, port = address
        elif isinstance(address, (str, unicode)):
            host, port = address.split(':')
            port = int(port)
        else:
            raise ValueError('address, must be either a tuple/list or string of the name:port form')

        # if not isinstance(registry, dict):
        #     raise ValueError('registry must be a dictionary')

        self._registry = registry
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

    @abstractproperty
    def bound_address(self):
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
    def receive(self, sock):
        try:
            request = sock.read()
            name, _id, args, kwargs = loads(request)
            result = False

            if name == '#INIT':
                try:
                    self._mutex.acquire()
                    _class = self._registry[_id]
                    instance = _class(*args, **kwargs)
                    instance_id = hash(instance)
                    self._registry[instance_id] = instance
                    result = instance_id
                    self._log.debug('=> INIT, instance id= {0}'.format(instance_id))
                finally:
                    self._mutex.release()
            elif name == '#DEL':
                self._log.debug('=> DEL')
                del self._registry[_id]
                result = True
            elif name == "#PING":
                self._log.debug('=> PING')
                result = True
            elif name == '#SHUTDOWN':
                self._log.debug('=> SHUTDOWN')
                self.shutdown()
                result = True
            elif name == '#DEBUG':
                self._log.debug('''
------------------------------------------------------------------------------------------------------------------------
REGISTRY:
{0}
------------------------------------------------------------------------------------------------------------------------
'''.format(pformat(self._registry)))
            else:
                instance = self._registry.get(_id, None)
                if not instance:
                    raise InvalidInstanceId('insance with id:{0} not registered'.format(_id))
                func = getattr(instance, name, None)
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

    def run(self):
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

    def run(self):
        self._log.info('starting ... ')
        self._manager.run()
