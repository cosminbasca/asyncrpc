import traceback
from tornado.concurrent import Future
from asyncrpc.exceptions import current_error
from asyncrpc.messaging import loads, dumps
from asyncrpc.client import RpcProxy, asynchronous
from asyncrpc.handler import RpcHandler
from asyncrpc.log import get_logger
from tornado.ioloop import IOLoop
from tornado.httpclient import AsyncHTTPClient, HTTPError, HTTPClient
from tornado import gen
from tornado import web

__author__ = 'basca'

USE_CURL = True
if USE_CURL:
    try:
        from tornado.curl_httpclient import CurlAsyncHTTPClient

        AsyncHTTPClient.configure(CurlAsyncHTTPClient)
    except ImportError:
        pass

# ----------------------------------------------------------------------------------------------------------------------
#
#
#
# ----------------------------------------------------------------------------------------------------------------------
class TornadoHttpRpcProxy(RpcProxy):
    def __init__(self, address, slots=None, **kwargs):
        super(TornadoHttpRpcProxy, self).__init__(address, slots=slots, **kwargs)

    def _status_code(self, response):
        return response.code

    def _content(self, response):
        return response.body

    def _http_call(self, message):
        http_client = HTTPClient()
        try:
            response = http_client.fetch(self.url, body=message, method='POST',
                                         connect_timeout=300, request_timeout=300)
        except HTTPError as e:
            self._log.error("HTTP Error: {0}".format(e))
            raise e
        finally:
            http_client.close()
        return response


# ----------------------------------------------------------------------------------------------------------------------
#
#
#
# ----------------------------------------------------------------------------------------------------------------------
class TornadoAsyncHttpRpcProxy(RpcProxy):
    def __init__(self, address, slots=None, **kwargs):
        super(TornadoAsyncHttpRpcProxy, self).__init__(address, slots=slots, **kwargs)

    def _status_code(self, response):
        return response.code

    def _content(self, response):
        return response.body

    @gen.coroutine
    def _http_call(self, message):
        http_client = AsyncHTTPClient()
        try:
            response = yield http_client.fetch(self.url, body=message, method='POST', connect_timeout=300,
                                               request_timeout=300)
        except HTTPError as e:
            self._log.error("HTTP Error: {0}".format(e))
            raise e
        finally:
            http_client.close()
        raise gen.Return(response)

    @gen.coroutine
    def _rpc_call(self, name, *args, **kwargs):
        self._log.debug("calling {0}".format(name))
        response = yield self._http_call(self._message(name, *args, **kwargs))
        raise gen.Return(self._get_result(response))


# ----------------------------------------------------------------------------------------------------------------------
#
#
#
# ----------------------------------------------------------------------------------------------------------------------
class TornadoProxyFactory(object):
    def __init__(self):
        self._log = get_logger(TornadoProxyFactory.__class__.__name__)
        self._async_cache = dict()
        self._cache = dict()
        self._log.debug("tornado proxy factory initialized")

    @staticmethod
    def instance():
        if not hasattr(TornadoProxyFactory, "_instance"):
            TornadoProxyFactory._instance = TornadoProxyFactory()
        return TornadoProxyFactory._instance

    def async_proxy(self, address):
        proxy = self._async_cache.get(address, None)
        if proxy is None:
            proxy = TornadoAsyncHttpRpcProxy(address)
            self._async_cache[address] = proxy
        return proxy

    def proxy(self, address):
        proxy = self._cache.get(address, None)
        if proxy is None:
            proxy = TornadoHttpRpcProxy(address)
            self._cache[address] = proxy
        return proxy


def async_call(address):
    return TornadoProxyFactory.instance().async_proxy(address)


def call(address):
    return TornadoProxyFactory.instance().proxy(address)


# ----------------------------------------------------------------------------------------------------------------------
#
#
#
# ----------------------------------------------------------------------------------------------------------------------
class TornadoRequestHandler(web.RequestHandler, RpcHandler):
    def __init__(self, application, request, **kwargs):
        super(TornadoRequestHandler, self).__init__(application, request, **kwargs)
        if not isinstance(application, TornadoRpcApplication):
            raise ValueError('application must be an instance of TornadoRpcApplication')
        self._instance = application.instance
        self._logger = get_logger(self.__class__.__name__)

    def get_instance(self, *args, **kwargs):
        return self._instance

    @gen.coroutine
    def post(self, *args, **kwargs):
        try:
            name, args, kwargs = loads(self.request.body)
            self._logger.debug('calling function: "{0}"'.format(name))
            result = self.rpc()(name, *args, **kwargs)
            if isinstance(result, Future):
                result = yield result
            error = None
        except Exception, e:
            error = current_error()
            result = None
            self._logger.error('error: {0}, traceback: \n{1}'.format(e, traceback.format_exc()))
        response = dumps((result, error))
        self.write(response)


# ----------------------------------------------------------------------------------------------------------------------
#
#
#
# ----------------------------------------------------------------------------------------------------------------------
class TornadoRpcApplication(web.Application):
    def __init__(self, instance, handlers=None, default_host="", transforms=None, wsgi=False, **settings):
        super(TornadoRpcApplication, self).__init__(handlers=handlers, default_host=default_host, transforms=transforms,
                                                    wsgi=wsgi, **settings)
        self._instance = instance

    instance = property(fget=lambda self: self._instance)


# ----------------------------------------------------------------------------------------------------------------------
#
#
#
# ----------------------------------------------------------------------------------------------------------------------
class TornadoRpcServer(object):
    def __init__(self, instance, port=8080):
        self.app = TornadoRpcApplication(instance, handlers=[
            web.url(r"/rpc", TornadoRequestHandler)
        ])
        self.port = port

    def start(self):
        self.app.listen(self.port)
        IOLoop.current().start()


# ----------------------------------------------------------------------------------------------------------------------
#
# testing
#
# ----------------------------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    class AClass(object):
        def do_x(self, x=10):
            return x

        def do_other(self, y):
            return self.do_x() * y

        @gen.coroutine
        def do_async(self, remote_addr, x, y):
            proxy = TornadoAsyncHttpRpcProxy(remote_addr)
            value1 = yield proxy.do_x(x)
            print 'got value 1 = ', value1
            value2 = yield proxy.do_x(y)
            print 'got value 2 = ', value2
            result = value1 + value2
            raise gen.Return(result)

    instance = AClass()
    srv = TornadoRpcServer(instance)
    srv.start()