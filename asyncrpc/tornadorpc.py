from functools import partial
from asyncrpc.client import RpcProxy
from asyncrpc.messaging import dumps
from tornado.httpclient import AsyncHTTPClient, HTTPError
from tornado.curl_httpclient import CurlAsyncHTTPClient

__author__ = 'basca'

USE_CURL = True
if USE_CURL:
    AsyncHTTPClient.configure(CurlAsyncHTTPClient)

class TornadoHttpRpcProxy(RpcProxy):
    def __init__(self, address, slots=None, **kwargs):
        super(TornadoHttpRpcProxy, self).__init__(None, address, slots=slots, owner=False, **kwargs)
        self._func_url = partial('{0}/{2}'.format, self._url_path)

    def _status_code(self, response):
        pass

    def _content(self, response):
        pass

    def _httpcall(self, message):
        http_client = AsyncHTTPClient()
        try:
            response = http_client.fetch(self._func_url(name))
            print response.body
        except HTTPError as e:
            print "Error:", e
        http_client.close()

    def _message(self, name, *args, **kwargs):
        return dumps((name, args, kwargs))


class TornadoRpcServer(object):
    def __init__(self, request_handler):
        pass