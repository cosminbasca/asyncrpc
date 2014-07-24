from abc import ABCMeta, abstractmethod, abstractproperty
import os
import sys
from tornado.netutil import bind_sockets
from cherrypy.wsgiserver import CherryPyWSGIServer
from tornado.wsgi import WSGIContainer
from tornado.httpserver import HTTPServer
from tornado import ioloop
from asyncrpc.wsgi import RpcRegistryMiddleware, RpcRegistryViewer
from asyncrpc.log import get_logger
from asyncrpc.registry import Registry
from werkzeug.wsgi import DispatcherMiddleware
from werkzeug.debug import DebuggedApplication

# ----------------------------------------------------------------------------------------------------------------------
#
# Base RPC Server
#
# ----------------------------------------------------------------------------------------------------------------------
class RpcServer(object):
    __metaclass__ = ABCMeta

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
# Wsgi RPC server setup
#
# ----------------------------------------------------------------------------------------------------------------------
class WsgiRpcServer(RpcServer):
    __metaclass__ = ABCMeta

    def __init__(self, address, registry, debug=True, *args, **kwargs):
        if isinstance(registry, dict):
            registry = Registry(**registry)
        if not isinstance(registry, Registry):
            raise ValueError('registry must be a Registry')
        super(WsgiRpcServer, self).__init__(address, *args, **kwargs)

        registry_app = RpcRegistryMiddleware(registry, shutdown_callback=self.shutdown)
        registry_viewer = RpcRegistryViewer(registry, with_static=True)
        if debug:
            registry_viewer = DebuggedApplication(registry_viewer, evalex=True)
        wsgi_app = DispatcherMiddleware(registry_viewer, {'/rpc': registry_app})
        self._init_wsgi_server(self.address, wsgi_app, *args, **kwargs)

    @abstractmethod
    def _init_wsgi_server(self, address, wsgi_app, *args, **kwargs):
        pass


# ----------------------------------------------------------------------------------------------------------------------
#
# Cherrypy RPC implementation
#
# ----------------------------------------------------------------------------------------------------------------------
class CherrypyRpcServer(WsgiRpcServer):
    def _init_wsgi_server(self, address, wsgi_app, *args, **kwargs):
        self._server = CherryPyWSGIServer(address, wsgi_app)
        self._bound_address = None

    def close(self):
        self._server.stop()

    def server_forever(self, *args, **kwargs):
        self._log.info('starting cherrypy server with a minimum of {0} threads and {1} max threads'.format(
            self._server.numthreads, self._server.maxthreads if self._server.maxthreads else 'no'))
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
        if not self._bound_address:
            sock = getattr(self._server, 'socket', None)
            if sock:
                self._bound_address = sock.getsockname()
            else:
                return self._address
        return self._bound_address


# ----------------------------------------------------------------------------------------------------------------------
#
# Tornado RPC implementation
#
# ----------------------------------------------------------------------------------------------------------------------
class TornadoRpcServer(WsgiRpcServer):
    def _init_wsgi_server(self, address, wsgi_app, *args, **kwargs):
        self._server = HTTPServer(WSGIContainer(wsgi_app))
        self._sockets = bind_sockets(address[1], address=address[0])
        self._server.add_sockets(self._sockets)
        self._bound_address = self._sockets[0].getsockname()  # get the bound address of the first socket ...

    def close(self):
        ioloop.IOLoop.instance().stop()

    def server_forever(self, *args, **kwargs):
        self._log.info(
            'starting tornado server in single-process mode')
        try:
            ioloop.IOLoop.instance().start()
        except Exception, e:
            self._log.error("exception in serve_forever: {0}".format(e))
        finally:
            self._log.info('closing the server ...')
            self.close()
            self._log.info('server shutdown complete')

    @property
    def bound_address(self):
        return self._bound_address


if __name__ == '__main__':
    # set_level('critical')
    import numpy as np

    class MyClass(object):
        def __init__(self, counter=0, wait=False):
            self._c = counter
            self._w = wait
            self.some_data = [10, 20, '30', 'hehe']
            # print 'with wait = ', True if self._w else False

        @property
        def a_property(self):
            return {'un':1, 'doi':2}

        def add(self, value=1):
            self._c += value

        def dec(self, value=1):
            self._c -= value

        def current_counter(self):
            # if self._w: sleep(random() * 0.8) # between 0 and .8 seconds
            # if self._w: self._c = sum([i ** 2 for i in xrange(int(random() * 100000))])  # a computation ...
            if self._w: self._c = np.exp(np.arange(1000000)).sum()
            return self._c

    registry = {'MyClass': MyClass}
    cpsrv = CherrypyRpcServer(('127.0.0.1', 8080), registry)
    # cpsrv = CherrypyRpcServer(('127.0.0.1', 0), registry)
    # cpsrv = TornadoRpcServer(('127.0.0.1', 8080), registry)
    # cpsrv = TornadoRpcServer(('127.0.0.1', 8080), registry)
    # print 'BOUND to PORT = {0}'.format(cpsrv.bound_address)
    cpsrv.start()