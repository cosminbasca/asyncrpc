import traceback
from tornado.concurrent import Future
from tornado.httpserver import HTTPServer
from tornado.netutil import bind_sockets
from asyncrpc.server import RpcServer
from asyncrpc.process import BackgroundRunner
from asyncrpc.exceptions import current_error, RpcServerNotStartedException
from asyncrpc.messaging import loads, dumps
from asyncrpc.client import RpcProxy
from asyncrpc.handler import RpcHandler
from asyncrpc.log import get_logger, set_level
from tornado.ioloop import IOLoop
from tornado.httpclient import AsyncHTTPClient, HTTPError, HTTPClient
from tornado import gen
from tornado import web

__author__ = 'basca'

# USE_CURL = True
USE_CURL = False
if USE_CURL:
    try:
        from tornado.curl_httpclient import CurlAsyncHTTPClient

        AsyncHTTPClient.configure(CurlAsyncHTTPClient)
    except ImportError:
        pass

# ----------------------------------------------------------------------------------------------------------------------
#
# synchronous tornado http rpc proxy
#
# ----------------------------------------------------------------------------------------------------------------------
class TornadoHttpRpcProxy(RpcProxy):
    def __init__(self, address, slots=None, **kwargs):
        """
        an HTTP RPC proxy based on the tornado synchronous HTTPClient

        :param address: a (host,port) tuple
        :param slots: the list of method names the proxy is restricted to
        :param kwargs: named arguments (passed forward to the RpcProxy base class
        :return: the synchronous tornado HTTP RPC proxy
        """
        super(TornadoHttpRpcProxy, self).__init__(address, slots=slots, **kwargs)

    def _status_code(self, response):
        """
        extracts and returns the HTTP response's status code
        :param response: an instance of a tornado HTTPResponse
        :return: the HTTP status code
        """
        return response.code

    def _content(self, response):
        """
        extracts and returns the HTTP response's body
        :param response: and instance of a tornado HTTPResponse
        :return: the HTTPResponse body
        """
        return response.body

    def _http_call(self, message):
        """
        the HTTP RPC call
        :param message: the message to send to the RPC server (usually an encoded tuple of method_name, args, kwargs)
        :return: the HTTP server response
        """
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
# asynchronous tornado http rpc proxy
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


def async_call(address):
    """
    create and perform an asynchronous HTTP RPC call to a tornado (single instance) RPC server
    :param address: a (host,port) tuple
    :return: a tornado Future of the RPC response (or an error otherwise)
    """
    return TornadoAsyncHttpRpcProxy(tuple(address))


def call(address):
    """
    create and perform a synchronous HTTP RPC call to a tornado (single instance) RCP server
    :param address: a (host,port) tuple
    :return: the actual RPC response (or an error otherwise)
    """
    return TornadoHttpRpcProxy(tuple(address))


# ----------------------------------------------------------------------------------------------------------------------
#
# http rpc tornado request handler
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


class PingRequestHandler(web.RequestHandler):
    def get(self, *args, **kwargs):
        self.write('pong')

    def post(self, *args, **kwargs):
        self.write('pong')


# ----------------------------------------------------------------------------------------------------------------------
#
# http rpc tornado application
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
# single instance http rpc tornado server
#
# ----------------------------------------------------------------------------------------------------------------------
class TornadoRpcServer(RpcServer):
    def __init__(self, address, instance, multiprocess=False, *args, **kwargs):
        super(TornadoRpcServer, self).__init__(address, *args, **kwargs)
        app = TornadoRpcApplication(instance, handlers=[
            web.url(r"/rpc", TornadoRequestHandler),
            web.url(r"/ping", PingRequestHandler),
        ])
        self._multiprocess = multiprocess
        self._server = HTTPServer(app)
        self._sockets = bind_sockets(address[1], address=address[0])
        if not self._multiprocess:
            self._server.add_sockets(self._sockets)
        self._bound_address = self._sockets[0].getsockname()

    def close(self):
        IOLoop.instance().stop()

    def server_forever(self, *args, **kwargs):
        try:
            if self._multiprocess:
                self._log.info('starting tornado server in multi-process mode')
                self._server.start(0)
                self._server.add_sockets(self._sockets)
            else:
                self._log.info('starting tornado server in single-process mode')
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


class TornadoManager(object):
    def __init__(self, instance, address=('127.0.0.1', 0), async=False, gevent_patch=False, retries=100, **kwargs):
        self._log = get_logger(self.__class__.__name__)
        self._async = async
        self._instance = instance
        self._runner = BackgroundRunner(server_class=TornadoRpcServer, address=address, gevent_patch=gevent_patch,
                                        retries=retries)

    def proxy(self, slots=None, **kwargs):
        if not self._runner.is_running:
            raise RpcServerNotStartedException('the tornado rcp server has not been started!')
        _Proxy = TornadoAsyncHttpRpcProxy if self._async else TornadoHttpRpcProxy
        return _Proxy(self.bound_address, slots=slots, **kwargs)

    def __del__(self):
        self._runner.stop()

    def start(self, wait=True, **kwargs):
        self._runner.start(wait, self._instance, **kwargs)

    def stop(self):
        self._runner.stop()

    @property
    def bound_address(self):
        return self._runner.bound_address


# ----------------------------------------------------------------------------------------------------------------------
#
# testing
#
# ----------------------------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    set_level('critical')

    class AClass(object):
        def do_x(self, x=10):
            return x

        def do_other(self, y):
            return self.do_x() * y

        @gen.coroutine
        def do_async(self, remote_addr, x, y):
            value1 = yield async_call(remote_addr).do_x(x)
            # value2 = yield async_call(remote_addr).do_x(y)
            # result = value1 + value2
            result = value1 + y
            raise gen.Return(result)

        def do_sync(self, remote_addr, x, y):
            value1 = call(remote_addr).do_x(x)
            result = value1 + y
            return result

    instance = AClass()
    man = TornadoManager(instance)
    man.start()

    px = man.proxy()
    print px.do_x(x=20)
    print px.do_other(40)