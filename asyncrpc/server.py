from abc import ABCMeta, abstractmethod, abstractproperty
import os
import sys
from tornado.netutil import bind_sockets
from cherrypy.wsgiserver import CherryPyWSGIServer, WSGIPathInfoDispatcher
from tornado.wsgi import WSGIContainer
from tornado.httpserver import HTTPServer
from tornado import ioloop
from asyncrpc.wsgi import RpcRegistryMiddleware
from asyncrpc.log import get_logger, set_level
from asyncrpc.__version__ import str_version
from werkzeug.wsgi import DispatcherMiddleware
from werkzeug.wrappers import Request, Response

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


def default(environ, start_response):
    request = Request(environ)
    text = 'Welcome to asyncrpc version {0}'.format(str_version)
    response = Response(text, mimetype='text/plain')
    return response(environ, start_response)


# ----------------------------------------------------------------------------------------------------------------------
#
# Cherrypy RPC implementation
#
# ----------------------------------------------------------------------------------------------------------------------
class CherrypyRpcServer(RpcServer):
    def __init__(self, address, registry, **kwargs):
        super(CherrypyRpcServer, self).__init__(address)
        self._registry_app = RpcRegistryMiddleware(registry, shutdown_callback=self.shutdown)
        # self._server = CherryPyWSGIServer(address, WSGIPathInfoDispatcher({'/rpc': self._registry_app}), **kwargs)
        self._server = CherryPyWSGIServer(address, DispatcherMiddleware(default, {'/rpc': self._registry_app}))

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
        self._server = HTTPServer(WSGIContainer(DispatcherMiddleware(default, {'/rpc': self._registry_app})))
        self._sockets = bind_sockets(address[1], address=address[0])
        self._server.add_sockets(self._sockets)
        self._bound_address = self._sockets[0].getsockname()  # get the bound address of the first socket ...
        self._multiprocess = multiprocess

    def close(self):
        ioloop.IOLoop.instance().stop()

    def server_forever(self, *args, **kwargs):
        self._log.info(
            'starting tornado server in {0} mode'.format('multi-process' if self._multiprocess else 'single-process'))
        try:
            if self._multiprocess:
                self._server.start(0)  # fork multiple processes
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
            # print 'with wait = ', True if self._w else False

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
    # cpsrv = CherrypyRpcServer(('127.0.0.1', 8080), registry)
    cpsrv = TornadoRpcServer(('127.0.0.1', 8080), registry, multiprocess=False)
    # print 'BOUND to PORT = {0}'.format(cpsrv.bound_address)
    cpsrv.server_forever()