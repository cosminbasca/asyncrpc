from abc import ABCMeta, abstractmethod, abstractproperty
import os
import sys
from tornado.netutil import bind_sockets
from asyncrpc.wsgi import RpcRegistryMiddleware
from cherrypy.wsgiserver import CherryPyWSGIServer, WSGIPathInfoDispatcher
from tornado.wsgi import WSGIContainer
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from asyncrpc.log import get_logger


# ----------------------------------------------------------------------------------------------------------------------
#
# Base RPC Server
#
# ----------------------------------------------------------------------------------------------------------------------
class RpcServer(object):
    __metaclass__ = ABCMeta

    public = ['port', 'host', 'address', 'close', 'bound_address', 'start', 'shutdown']

    def __init__(self, address, *args, **kwargs):
        if isinstance(address, (tuple, list)):
            host, port = address
        elif isinstance(address, (str, unicode)):
            host, port = address.split(':')
            port = int(port)
        else:
            raise ValueError('address, must be either a tuple/list or string of the name:port form')

        self._log = get_logger(self.__class__.__name__)
        self._address = (host, port)

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
    def server_forever(self, *args, **kwargs):
        pass

    def start(self, *args, **kwargs):
        self.server_forever(*args, **kwargs)

    def shutdown(self, os_exit=True):
        try:
            self.close()
        finally:
            if os_exit:
                os._exit(0)
            else:
                sys.exit(0)


# ----------------------------------------------------------------------------------------------------------------------
#
# Cherrypy RPC implementation
#
# ----------------------------------------------------------------------------------------------------------------------
class CherrypyRpcServer(RpcServer):
    def __init__(self, address, registry, minthreads=10, maxthreads=-1, **kwargs):
        super(CherrypyRpcServer, self).__init__(address)
        self._minthreads = minthreads
        self._maxthreads = maxthreads
        self._registry_app = RpcRegistryMiddleware(registry, shutdown_callback=self.shutdown)
        self._server = CherryPyWSGIServer(address, WSGIPathInfoDispatcher({'/': self._registry_app}),
                                          minthreads=self._minthreads, maxthreads=self._maxthreads)

    def close(self):
        self._server.stop()

    def server_forever(self, *args, **kwargs):
        self._log.info('starting cherrypy server with {0} min threads and {1} max threads'.format(self._minthreads,
                                                                                                  self._maxthreads))
        try:
            self._server.start()
        except Exception, e:
            self._log.error("exception in serve_forever: {0}".format(e))
        finally:
            self._log.info('closing the server ...')
            self.close()
            self._log.info('server shutdown complete')

    @property
    def bound_address(self):
        return self._server.bind_addr


# ----------------------------------------------------------------------------------------------------------------------
#
# Tornado RPC implementation
#
# ----------------------------------------------------------------------------------------------------------------------
class TornadoRpcServer(RpcServer):
    def __init__(self, address, registry, multiprocess=False, **kwargs):
        super(TornadoRpcServer, self).__init__(address)
        self._registry_app = RpcRegistryMiddleware(registry, shutdown_callback=self.shutdown)
        self._server = HTTPServer(address, WSGIContainer(WSGIPathInfoDispatcher({'/': self._registry_app})))
        self._sockets = bind_sockets(address[0], address=address[1])
        self._server.add_sockets(self._sockets)
        self._bound_address = self._sockets[0].getsockname()  # get the bound address of the first socket ...
        self._multiprocess = multiprocess

    def close(self):
        IOLoop.instance().stop()

    def server_forever(self, *args, **kwargs):
        self._log.info('starting tornado server')
        try:
            if self._multiprocess:
                self._server.start(0)  # fork multiple processes
            IOLoop.instance().start()
        except Exception, e:
            self._log.error("exception in serve_forever: {0}".format(e))
        finally:
            self._log.info('closing the server ...')
            self.close()
            self._log.info('server shutdown complete')

    @property
    def bound_address(self):
        return self._bound_address