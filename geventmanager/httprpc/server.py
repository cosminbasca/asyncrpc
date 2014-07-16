from geventmanager.httprpc.wsgi import RpcServer, RpcRegistry
from cherrypy.wsgiserver import CherryPyWSGIServer, WSGIPathInfoDispatcher
from tornado.wsgi import WSGIContainer
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop


class CherrypyRpcServer(RpcServer):
    def __init__(self, address, registry, minthreads=10, maxthreads=-1, **kwargs):
        super(CherrypyRpcServer, self).__init__(address)
        self._minthreads = minthreads
        self._maxthreads = maxthreads
        self._registry_app = RpcRegistry(registry, shutdown_callback=None)
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


class TornadoRpcServer(RpcServer):
    def __init__(self, address, registry, **kwargs):
        super(TornadoRpcServer, self).__init__(address)
        self._registry_app = RpcRegistry(registry, shutdown_callback=None)
        self._server = HTTPServer(address, WSGIContainer(WSGIPathInfoDispatcher({'/': self._registry_app})))
        port, host = address
        self._server.listen(port, address=host)

    def close(self):
        IOLoop.instance().stop()

    def server_forever(self, *args, **kwargs):
        self._log.info('starting tornado server')
        try:
            IOLoop.instance().start()
        except Exception, e:
            self._log.error("exception in serve_forever: {0}".format(e))
        finally:
            self._log.info('closing the server ...')
            self.close()
            self._log.info('server shutdown complete')

    @property
    def bound_address(self):
        # return self._server.bind_addr
        return None