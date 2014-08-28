from abc import ABCMeta, abstractmethod, abstractproperty
from collections import OrderedDict
from cherrypy import engine
from tornado.netutil import bind_sockets
from cherrypy.wsgiserver import CherryPyWSGIServer
from tornado.wsgi import WSGIContainer
from tornado.httpserver import HTTPServer
from tornado import ioloop
from asyncrpc.wsgi import RpcRegistryMiddleware, RpcRegistryViewer, ping_middleware
from asyncrpc.log import get_logger, logger
from asyncrpc.registry import Registry
from werkzeug.wsgi import DispatcherMiddleware
from werkzeug.debug import DebuggedApplication
from requests import get, post

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

        self._log = get_logger(owner=self)
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
    def stop(self):
        pass

    @abstractproperty
    def bound_address(self):
        pass

    @abstractmethod
    def server_forever(self, *args, **kwargs):
        pass

    def start(self, *args, **kwargs):
        self.server_forever(*args, **kwargs)

    @staticmethod
    def is_online(address, method='get'):
        _http = get if method=='get' else post
        response = _http('http://{0}:{1}/ping'.format(address[0], address[1]))
        if response.status_code == 200:
            return response.content.strip().lower() == 'pong'
        return False


# ----------------------------------------------------------------------------------------------------------------------
#
# Wsgi RPC server setup
#
# ----------------------------------------------------------------------------------------------------------------------
class WsgiRpcServer(RpcServer):
    __metaclass__ = ABCMeta

    def __init__(self, address, types_registry, debug=True, theme=None, *args, **kwargs):
        if not isinstance(types_registry, (dict, OrderedDict)):
            raise ValueError('types_registry must be a dict or OrderDict')
        super(WsgiRpcServer, self).__init__(address, *args, **kwargs)

        self._registry = Registry()
        registry_app = RpcRegistryMiddleware(types_registry, self._registry)
        registry_viewer = RpcRegistryViewer(types_registry, self._registry, with_static=True, theme=theme)
        if debug:
            registry_viewer = DebuggedApplication(registry_viewer, evalex=True)
        wsgi_app = DispatcherMiddleware(registry_viewer, {
            '/rpc': registry_app,
            '/ping': ping_middleware,
        })
        self._init_wsgi_server(self.address, wsgi_app, *args, **kwargs)

    @abstractmethod
    def _init_wsgi_server(self, address, wsgi_app, *args, **kwargs):
        pass

    def stop(self):
        self._registry.clear()

# ----------------------------------------------------------------------------------------------------------------------
#
# Cherrypy RPC implementation
#
# ----------------------------------------------------------------------------------------------------------------------
class CherrypyWsgiRpcServer(WsgiRpcServer):
    def _init_wsgi_server(self, address, wsgi_app, *args, **kwargs):
        self._server = CherryPyWSGIServer(address, wsgi_app)
        self._bound_address = None

    def stop(self):
        super(CherrypyWsgiRpcServer, self).stop()
        self._server.stop()
        # engine.stop()
        engine.exit()

    def server_forever(self, *args, **kwargs):
        self._log.info('starting cherrypy server with a minimum of {0} threads and {1} max threads'.format(
            self._server.numthreads, self._server.maxthreads if self._server.maxthreads else 'no'))
        try:
            self._server.start()
        except Exception, e:
            self._log.error("exception in serve_forever: {0}".format(e))
        finally:
            self._log.info('closing the server ...')
            self.stop()
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
def shutdown_tornado(loop):
    loop.stop()

class TornadoWsgiRpcServer(WsgiRpcServer):
    def _init_wsgi_server(self, address, wsgi_app, *args, **kwargs):
        self._server = HTTPServer(WSGIContainer(wsgi_app))
        self._sockets = bind_sockets(address[1], address=address[0])
        self._server.add_sockets(self._sockets)
        self._bound_address = self._sockets[0].getsockname()  # get the bound address of the first socket ...

    def stop(self):
        super(TornadoWsgiRpcServer, self).stop()
        self._server.stop()
        loop = ioloop.IOLoop.instance()
        loop.add_callback(shutdown_tornado, loop)

    def server_forever(self, *args, **kwargs):
        self._log.info(
            'starting tornado server in single-process mode')
        try:
            ioloop.IOLoop.instance().start()
        except Exception, e:
            self._log.error("exception in serve_forever: {0}".format(e))
        finally:
            self._log.info('closing the server ...')
            self.stop()
            self._log.info('server shutdown complete')

    @property
    def bound_address(self):
        return self._bound_address

