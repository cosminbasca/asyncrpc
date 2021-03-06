#
# author: Cosmin Basca
#
# Copyright 2010 University of Zurich
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
from abc import ABCMeta, abstractmethod, abstractproperty
from collections import OrderedDict
from threading import Thread
from time import sleep
from cherrypy import engine
from tornado.netutil import bind_sockets
from cherrypy.wsgiserver import CherryPyWSGIServer
from tornado.wsgi import WSGIContainer
from tornado.httpserver import HTTPServer
from tornado import ioloop
from asyncrpc.wsgi import RpcRegistryMiddleware, RpcRegistryViewer, ping_middleware, RpcInstanceMiddleware, \
    info_middleware
from asyncrpc.registry import Registry
from asyncrpc.log import debug, warn, info, error
from werkzeug.wsgi import DispatcherMiddleware
from werkzeug.debug import DebuggedApplication
from requests import get, post, RequestException

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


def server_is_online(address, method='get', log_error=True):
    if isinstance(address, (tuple, list)):
        host, port = address
    elif isinstance(address, (str, unicode)):
        host, port = address.split(':')
        port = int(port)
    else:
        raise ValueError('address, must be either a tuple/list or string of the name:port form')

    _http = get if method == 'get' else post
    try:
        response = _http('http://{0}:{1}/ping'.format(host, port))
        if response.status_code == 200:
            return response.content.strip().lower() == 'pong'
        return False
    except RequestException as ex:
        if log_error:
            error('got an exception while checking if server is online: %s', ex)
        return False


def wait_for_server(address, method='get', check_every=0.5, timeout=None, to_start=True):
    def _test():
        return server_is_online(address, method=method, log_error=False) == to_start

    def _wait():
        while True:
            sleep(check_every)
            # noinspection PyBroadException
            try:
                if _test():
                    break
            except Exception:
                pass

    stopper = Thread(target=_wait)
    stopper.daemon = True
    stopper.start()
    stopper.join(timeout=timeout)


# ----------------------------------------------------------------------------------------------------------------------
#
# Wsgi RPC server setup
#
# ----------------------------------------------------------------------------------------------------------------------
class WsgiRpcServer(RpcServer):
    __metaclass__ = ABCMeta

    def __init__(self, address, model, debug=True, theme=None, *args, **kwargs):
        super(WsgiRpcServer, self).__init__(address, *args, **kwargs)
        if isinstance(model, (dict, OrderedDict)):
            types_registry = model
            self._model = Registry()
            registry_app = RpcRegistryMiddleware(types_registry, self._model)
            registry_viewer = RpcRegistryViewer(types_registry, self._model, with_static=True, theme=theme)
            if debug:
                registry_viewer = DebuggedApplication(registry_viewer, evalex=True)
            wsgi_app = DispatcherMiddleware(registry_viewer, {
                '/rpc': registry_app,
                '/ping': ping_middleware,
            })
        else:
            self._model = model
            instance_app = RpcInstanceMiddleware(self._model)
            if debug:
                instance_app = DebuggedApplication(instance_app, evalex=True)
            wsgi_app = DispatcherMiddleware(info_middleware, {
                '/rpc': instance_app,
                '/ping': ping_middleware,
            })
        self._init_wsgi_server(self.address, wsgi_app, *args, **kwargs)

    @abstractmethod
    def _init_wsgi_server(self, address, wsgi_app, *args, **kwargs):
        pass

    def stop(self):
        if hasattr(self._model, 'clear'):
            self._model.clear()

# ----------------------------------------------------------------------------------------------------------------------
#
# Cherrypy RPC implementation
#
# ----------------------------------------------------------------------------------------------------------------------
class CherrypyWsgiRpcServer(WsgiRpcServer):
    def __init__(self, address, model, *args, **kwargs):
        super(CherrypyWsgiRpcServer, self).__init__(address, model, *args, **kwargs)
        self._bound_address = None

    def _init_wsgi_server(self, address, wsgi_app, *args, **kwargs):
        self._server = CherryPyWSGIServer(address, wsgi_app)

    def stop(self):
        super(CherrypyWsgiRpcServer, self).stop()
        self._server.stop()
        # engine.stop()
        engine.exit()

    def server_forever(self, *args, **kwargs):
        info('starting cherrypy server with a minimum of %s threads and %s max threads',
            self._server.numthreads, self._server.maxthreads if self._server.maxthreads else 'no')
        try:
            self._server.start()
        except Exception, e:
            error("exception in serve_forever: %s", e)
        finally:
            info('closing the server ...')
            self.stop()
            info('server shutdown complete')

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
def shutdown_tornado(loop, server):
    if server:
        server.stop()
    loop.stop()


class TornadoWsgiRpcServer(WsgiRpcServer):
    def _init_wsgi_server(self, address, wsgi_app, *args, **kwargs):
        self._server = HTTPServer(WSGIContainer(wsgi_app))
        self._sockets = bind_sockets(address[1], address=address[0])
        self._server.add_sockets(self._sockets)
        self._bound_address = self._sockets[0].getsockname()  # get the bound address of the first socket ...

    def stop(self):
        super(TornadoWsgiRpcServer, self).stop()
        loop = ioloop.IOLoop.instance()
        loop.add_callback(shutdown_tornado, loop, self._server)

    def server_forever(self, *args, **kwargs):
        info('starting tornado server in single-process mode')
        try:
            ioloop.IOLoop.instance().start()
        except Exception, e:
            error("exception in serve_forever: %s", e)
        finally:
            info('closing the server ...')
            self.stop()
            info('server shutdown complete')

    @property
    def bound_address(self):
        return self._bound_address

