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

__author__ = 'basca'


def _command(name):
    return '#cmd:{0}#'.format(name)


_CMD_SHUTDOWN = _command('shutdown')
_CMD_PING = _command('ping')
_CMD_CLOSE_CONN = _command('close_conn')
_INIT_ROBJ = _command('init_robj')


# ----------------------------------------------------------------------------------------------------------------------
#
# base Rpc server api
#
# ----------------------------------------------------------------------------------------------------------------------
class RpcServer(object):
    __metaclass__ = ABCMeta

    def __init__(self, address, rpc_handler, **kwargs):
        if isinstance(address, (tuple, list)):
            host, port = address
        elif isinstance(address, (str, unicode)):
            host, port = address.split(':')
            port = int(port)
        else:
            raise ValueError('address, must be either a tuple/list or string of the name:port form')

        if not isinstance(rpc_handler, type):
            raise ValueError('rpc_handler must be an instance!')

        self.rpc_handler = rpc_handler
        self._address = (host, port)

        methods = inspect.getmembers(self.rpc_handler, predicate=inspect.ismethod)
        self._methods = set([method_name for method_name, impl in methods if not method_name.startswith('_')])

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

    def shutdown(self):
        try:
            self.close()
        finally:
            # sys.exit(0)
            os._exit(0)

    # noinspection PyBroadException
    def handle_rpc(self, sock):
        try:
            request = sock.read()
            name, args, kwargs = loads(request)

            if name == _CMD_PING:
                self._log.debug('received PING')
                result = True
            elif name == _CMD_CLOSE_CONN:
                self._log.debug('received CLOSE_CONN')
                result = True
            elif name == _CMD_SHUTDOWN:
                self._log.debug('received SHUTDOWN')
                self.shutdown()
                result = True
            elif name not in self._methods:
                raise NameError('method "{0}" not found in handler object'.format(name))
            else:
                func = getattr(self.rpc_handler, name)
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
    def __init__(self, address, rpc_handler, threads=1024, backlog=64):
        super(ThreadedRpcServer, self).__init__(address, rpc_handler)
        self._semaphore = BoundedSemaphore(value=threads)
        self._sock = InetRpcSocket()
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # self._sock.settimeout(None)
        self._sock.setblocking(1)
        self._sock.bind(self._address)
        self._backlog = backlog

    address = property(fget=lambda self: self._address)

    def close(self):
        self._sock.close()
        if hasattr(self.rpc_handler, 'close'):
            self.rpc_handler.close()

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
class RpcHandlerChild(preforkserver.BaseChild):
    _methods = None
    rpc_handler = None
    shutdown = None

    # def initialize(self):
    # def handle_terminate(signum, frame):
    # logger.info('SIGTERM received for child process [%s]'%(os.getpid()))
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


class PreforkedRpcServer(RpcServer, LoggerMixin):
    def __init__(self, host, rpc_handler, backlog=DEFAULT_SOCK_BACKLOG,
                 maxServers=cpu_count() * 2,
                 minServers=cpu_count(),
                 minSpareServers=cpu_count(),
                 maxSpareServers=cpu_count(),
                 maxRequests=0):
        super(PreforkedRpcServer, self).__init__(host, rpc_handler)

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
