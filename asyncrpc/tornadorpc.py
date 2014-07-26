from functools import partial
from asyncrpc.client import RpcProxy
from tornado.httpclient import AsyncHTTPClient, HTTPError
from tornado.curl_httpclient import CurlAsyncHTTPClient

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


class TornadoRpcServer(object):
    def __init__(self, request_handler):
        pass