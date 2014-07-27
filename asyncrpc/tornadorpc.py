from functools import partial
import traceback
from asyncrpc.exceptions import current_error
from asyncrpc.messaging import loads, dumps
from asyncrpc.client import RpcProxy, exposed_methods
from asyncrpc.handler import RpcHandler
from asyncrpc.log import get_logger
from tornado.httpclient import AsyncHTTPClient, HTTPError
from tornado.curl_httpclient import CurlAsyncHTTPClient
from tornado import gen
from tornado import web

__author__ = 'basca'

USE_CURL = True
if USE_CURL:
    AsyncHTTPClient.configure(CurlAsyncHTTPClient)


class TornadoHttpRpcProxy(RpcProxy):
    def __init__(self, address, slots=None, **kwargs):
        super(TornadoHttpRpcProxy, self).__init__(address, slots=slots, **kwargs)
        self._method_url = partial('{0}/{2}'.format, self._url_path)

    def _status_code(self, response):
        return response.code

    def _content(self, response):
        return response.body

    def _http_call(self, name, message):
        http_client = AsyncHTTPClient()
        try:
            response = http_client.fetch(self._method_url(name), body=message, method='POST',
                                         connect_timeout=300, request_timeout=300)
        except HTTPError as e:
            self._log.error("HTTP Error: {0}".format(e))
            raise e
        finally:
            http_client.close()
        return response

    def _rpc_call(self, name, *args, **kwargs):
        response = self._http_call(name, self._message(name, *args, **kwargs))
        return self._get_result(response)


class TornadoRequestHandler(web.RequestHandler, RpcHandler):
    def __init__(self, application, request, **kwargs):
        super(TornadoRequestHandler, self).__init__(application, request, **kwargs)
        if not isinstance(application, TornadoRpcApplication):
            raise ValueError('application must be an instance of TornadoRpcApplication')
        self._instance = application.instance
        self._async_methods = set([
            name for name, impl in exposed_methods(self._instance, with_private=False)
            if hasattr(impl, "asynchronous")
        ])
        self._log = get_logger(self.__class__.__name__)

    def get_instance(self, *args, **kwargs):
        return self._instance

    @gen.coroutine
    def post(self, *args, **kwargs):
        try:
            name, args, kwargs = loads(self.request.body)
            self._log.debug('calling function: "{0}"'.format(name))
            result = self.rpc()(name, *args, **kwargs)
            error = None
        except Exception, e:
            error = current_error()
            result = None
            self._log.error('error: {0}, traceback: \n{1}'.format(e, traceback.format_exc()))
        response = dumps((result, error))
        self.write(response)


class TornadoRpcApplication(web.Application):
    def __init__(self, instance, **settings):
        super(TornadoRpcApplication, self).__init__(**settings)
        self._instance = instance

    instance = property(fget=lambda self: self._instance)


class TornadoRpcServer(object):
    def __init__(self, request_handler):
        pass