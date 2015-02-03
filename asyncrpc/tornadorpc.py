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
from abc import ABCMeta
from collections import OrderedDict
import inspect
import traceback
from tornado.concurrent import Future
from tornado.httpserver import HTTPServer
from tornado.netutil import bind_sockets
from tornado.process import fork_processes
from asyncrpc.__version__ import str_version
from asyncrpc.manager import SingleInstanceAsyncManager
from asyncrpc.server import RpcServer, shutdown_tornado
from asyncrpc.exceptions import RpcServerNotStartedException, handle_exception, ErrorMessage
from asyncrpc.messaging import loads, dumps
from asyncrpc.client import RpcProxy, exposed_methods, SingleCastHTTPTransport, MultiCastHTTPTransport, \
    DEFAULT_CONNECTION_TIMEOUT
from asyncrpc.handler import RpcHandler
from asyncrpc.util import get_templates_dir, get_static_dir
from asyncrpc.log import debug, info, warn, error
from tornado.ioloop import IOLoop
from tornado.httpclient import AsyncHTTPClient, HTTPError, HTTPClient
from tornado import gen
from tornado import web
from docutils.core import publish_parts
import cStringIO

__author__ = 'basca'

_IMPL_TORNADO_CURL = "tornado.curl_httpclient.CurlAsyncHTTPClient"

class TornadoConfig(object):
    def __init__(self):
        self._use_curl = False
        self._force_instance = False
        self._max_clients = 10
        self._max_buffer_size = None
        self._use_body_streaming = False
        self.apply()

    def apply(self):
        try:
            if self._use_curl:
                AsyncHTTPClient.configure(_IMPL_TORNADO_CURL, max_clients=self._max_clients)
            else:
                AsyncHTTPClient.configure(None, max_buffer_size=self._max_buffer_size)
        except ImportError, err:
            self._use_curl = False
            AsyncHTTPClient.configure(None, max_buffer_size=self._max_buffer_size)
            warn('could not configure Tornado Web to use cURL. Reason: %s', err)

    @property
    def use_curl(self):
        return self._use_curl

    @use_curl.setter
    def use_curl(self, value):
        self._use_curl = value

    @property
    def max_clients(self):
        return self._max_clients

    @max_clients.setter
    def max_clients(self, value):
        self._max_clients = value if value > 0 else None

    @property
    def force_instance(self):
        return self._force_instance

    @force_instance.setter
    def force_instance(self, value):
        self._force_instance = True if value else False

    @property
    def max_buffer_size(self):
        return self._max_buffer_size

    @max_buffer_size.setter
    def max_buffer_size(self, value):
        self._max_buffer_size = value if value > 0 else None

    @property
    def use_body_streaming(self):
        return self._use_body_streaming

    @use_body_streaming.setter
    def use_body_streaming(self, value):
        self._use_body_streaming = True if value else False

    @staticmethod
    def instance():
        if not hasattr(TornadoConfig, "_instance"):
            TornadoConfig._instance = TornadoConfig()
        return TornadoConfig._instance

# ----------------------------------------------------------------------------------------------------------------------
#
# asynchronous decorator alias
#
# ----------------------------------------------------------------------------------------------------------------------
asynchronous = gen.coroutine

# ----------------------------------------------------------------------------------------------------------------------
#
# Tornado Transport Classes
#
# ----------------------------------------------------------------------------------------------------------------------
class SynchronousTornadoHTTP(SingleCastHTTPTransport):
    def __init__(self, address, connection_timeout, **kwargs):
        super(SynchronousTornadoHTTP, self).__init__(address, connection_timeout)

    def __call__(self, message):
        http_client = HTTPClient()
        response = ('', None)
        try:
            response = http_client.fetch(self.url, body=message, method='POST',
                                         connect_timeout=self.connection_timeout,
                                         request_timeout=self.connection_timeout)
        except HTTPError as e:
            error("HTTP Error: %s, payload size (bytes): %s", e, len(message))
            handle_exception(ErrorMessage.from_exception(e, address=self.url))
        finally:
            http_client.close()
        return response

    def content(self, response):
        return response.body

    def status_code(self, response):
        return response.code


class MaxRetriesException(Exception):
    pass

class AsynchronousTornadoHTTP(SingleCastHTTPTransport):
    def __init__(self, address, connection_timeout, **kwargs):
        super(AsynchronousTornadoHTTP, self).__init__(address, connection_timeout, **kwargs)
        tcfg = TornadoConfig.instance()
        self._force_instance = tcfg.force_instance
        self._max_buffer_size = tcfg.max_buffer_size

    @gen.coroutine
    def __call__(self, message):
        http_client = AsyncHTTPClient(force_instance=self._force_instance)
        debug('client = %s, max_buffer_size = %s', http_client.__class__.__name__,
              getattr(http_client, 'max_buffer_size') if hasattr(http_client, 'max_buffer_size') else 'unsupported')
        response = ('', None)
        try:
            response = yield http_client.fetch(self.url, body=message, method='POST',
                                               connect_timeout=self.connection_timeout,
                                               request_timeout=self.connection_timeout)
        except HTTPError as e:
            error("HTTP Error: %s, payload size (bytes): %s", e, len(message))
            handle_exception(ErrorMessage.from_exception(e, address=self.url))
        finally:
            if self._force_instance:
                http_client.close()

        raise gen.Return(response)

    def content(self, response):
        return response.body

    def status_code(self, response):
        return response.code


class MulticastAsynchronousTornadoHTTP(MultiCastHTTPTransport):
    def __init__(self, address, connection_timeout, **kwargs):
        super(MulticastAsynchronousTornadoHTTP, self).__init__(address, connection_timeout, **kwargs)
        tcfg = TornadoConfig.instance()
        self._force_instance = tcfg.force_instance
        self._max_buffer_size = tcfg.max_buffer_size

    @gen.coroutine
    def __call__(self, message):
        clients = [( AsyncHTTPClient(force_instance=self._force_instance), url )
                   for url in self.urls]
        response = ('', None)
        try:
            response = yield [
                client.fetch(url, body=message, method='POST', connect_timeout=self.connection_timeout,
                             request_timeout=self.connection_timeout) for client, url in clients
            ]
        except HTTPError as e:
            error("HTTP Error: %s", e)
            handle_exception(ErrorMessage.from_exception(e, address=self.urls))
        finally:
            if self._force_instance:
                [client.close() for client, url in clients]
        raise gen.Return(response)

    def content(self, response):
        return response.body

    def status_code(self, response):
        return response.code

# ----------------------------------------------------------------------------------------------------------------------
#
# synchronous tornado http rpc proxy
#
# ----------------------------------------------------------------------------------------------------------------------
class TornadoHttpRpcProxy(RpcProxy):
    def __init__(self, address, slots=None, connection_timeout=DEFAULT_CONNECTION_TIMEOUT, transport_kwargs=None):
        super(TornadoHttpRpcProxy, self).__init__(address, slots=slots, connection_timeout=connection_timeout,
                                                  transport_kwargs=transport_kwargs)

    def get_transport(self, address, connection_timeout, **kwargs):
        return SynchronousTornadoHTTP(address, connection_timeout, **kwargs)


# ----------------------------------------------------------------------------------------------------------------------
#
# asynchronous tornado http rpc proxy
#
# ----------------------------------------------------------------------------------------------------------------------
class TornadoAsyncHttpRpcProxy(RpcProxy):
    def __init__(self, address, slots=None, connection_timeout=DEFAULT_CONNECTION_TIMEOUT, transport_kwargs=None):
        super(TornadoAsyncHttpRpcProxy, self).__init__(address, slots=slots, connection_timeout=connection_timeout,
                                                       transport_kwargs=transport_kwargs)

    def get_transport(self, address, connection_timeout, **kwargs):
        if isinstance(address, (list, set)):
            return MulticastAsynchronousTornadoHTTP(address, connection_timeout, **kwargs)
        return AsynchronousTornadoHTTP(address, connection_timeout, **kwargs)

    @gen.coroutine
    def _rpc_call(self, name, *args, **kwargs):
        debug('calling "%s"', name)
        response = yield self._transport(self._message(name, *args, **kwargs))
        result = self._process_response(response)
        raise gen.Return(result)


def async_call(address, connection_timeout=DEFAULT_CONNECTION_TIMEOUT):
    """
    create and perform an asynchronous HTTP RPC call to a tornado (single instance) RPC server
    :param address: a (host,port) tuple or "ip:port" string
    :return: a tornado Future of the RPC response (or an error otherwise)
    """
    return TornadoAsyncHttpRpcProxy(address, connection_timeout=connection_timeout)


def call(address, connection_timeout=DEFAULT_CONNECTION_TIMEOUT):
    """
    create and perform a synchronous HTTP RPC call to a tornado (single instance) RCP server
    :param address: a (host,port) tuple or "ip:port" string
    :return: the actual RPC response (or an error otherwise)
    """
    return TornadoHttpRpcProxy(address, connection_timeout=connection_timeout)


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

    def get_instance(self, *args, **kwargs):
        return self._instance

    @gen.coroutine
    def post(self, *args, **kwargs):
        try:
            name, args, kwargs = loads(self.request.body)
            debug('calling function: "%s"', name)
            result = self.rpc()(name, *args, **kwargs)
            if isinstance(result, Future):
                result = yield result
            execution_error = None
        except Exception, e:
            execution_error = ErrorMessage.from_exception(e, address='{0}://{1}'.format(self.request.protocol, self.request.host))
            result = None
            error('error: %s, traceback: \n%s', e, traceback.format_exc())
        response = dumps((result, execution_error))
        self.write(response)


@web.stream_request_body
class TornadoStreamingRequestHandler(web.RequestHandler, RpcHandler):
    def __init__(self, application, request, **kwargs):
        super(TornadoStreamingRequestHandler, self).__init__(application, request, **kwargs)
        if not isinstance(application, TornadoRpcApplication):
            raise ValueError('application must be an instance of TornadoRpcApplication')
        self._instance = application.instance
        self._buffer = None
        self._content_lenght = 0

    def get_instance(self, *args, **kwargs):
        return self._instance

    # noinspection PyBroadException
    def prepare(self):
        try:
            self._content_lenght = long(self.request.headers.get('Content-Length', '0'))
            self.request.connection.set_max_body_size(self._content_lenght)
            self._buffer = cStringIO.StringIO()
        except Exception as e:
            self._buffer.close()
            self._buffer = None
            self._content_lenght = 0
            error('got an Exception while setting up the content length of the request: %s', e)

    def data_received(self, data):
        self._buffer.write(data)

    def get_body(self):
        try:
            contents = self._buffer.getvalue()
            if len(contents) == self._content_lenght:
                return contents
            raise HTTPError('Content-Lenght: {0} and actual content length: {1} do not match'.format(
                            self._content_lenght, len(contents)))
        finally:
            self._buffer.close()
            self._buffer = None


    @gen.coroutine
    def post(self, *args, **kwargs):
        try:
            name, args, kwargs = loads(self.get_body())
            debug('calling function: "%s"', name)
            result = self.rpc()(name, *args, **kwargs)
            if isinstance(result, Future):
                result = yield result
            execution_error = None
        except Exception, e:
            execution_error = ErrorMessage.from_exception(e, address='{0}://{1}'.format(self.request.protocol, self.request.host))
            result = None
            error('error: %s, traceback: \n%s', e, traceback.format_exc())
        response = dumps((result, execution_error))
        self.write(response)


class PingRequestHandler(web.RequestHandler):
    def get(self, *args, **kwargs):
        self.write('pong')

    def post(self, *args, **kwargs):
        self.write('pong')


def decorated_nethods(cls, *decorator_names):
    _decorators = ['@' + name for name in decorator_names]
    sourcelines = inspect.getsourcelines(cls)[0]
    for i, line in enumerate(sourcelines):
        line = line.strip()
        if line.split('(')[0].strip() in _decorators:  # leaving a bit out
            next_line = sourcelines[i + 1]
            name = next_line.split('def')[1].split('(')[0].strip()
            yield (name)


class TornadoRpcRequestHandler(web.RequestHandler):
    __metaclass__ = ABCMeta

    def __init__(self, application, request, **kwargs):
        super(TornadoRpcRequestHandler, self).__init__(application, request, **kwargs)
        if not isinstance(application, TornadoRpcApplication):
            raise ValueError('application must be an instance of TornadoRpcApplication')
        self._instance = application.instance
        self._theme = application.theme


class InstanceViewerHandler(TornadoRpcRequestHandler):
    def get(self, *args, **kwargs):
        async_methods = set(decorated_nethods(self._instance.__class__, "asynchronous", "gen.coroutine"))
        methods = exposed_methods(self._instance, with_private=False)

        def _is_decorated(method_name):
            return method_name in async_methods

        def _argspec(methond_name, method_impl):
            if _is_decorated(methond_name):
                original = method_impl.func_closure[0].cell_contents
                spec = inspect.getargspec(original)
            else:
                spec = inspect.getargspec(method_impl)
            spec = spec._asdict()
            if spec['defaults']:
                r_defaults = list(reversed(spec['defaults']))
                r_args = list(reversed(spec['args']))
                spec['defaults'] = list(reversed([(r_args[i], val) for i, val in enumerate(r_defaults)]))
            return spec

        def _doc(method_impl):
            docstring = inspect.getdoc(method_impl)
            if docstring:
                docstring = '\n\t'.join([line.strip() for line in docstring.split('\n')])
                return publish_parts(docstring, writer_name='html')['fragment'].replace('param', '')
            return '&nbsp;'

        api = OrderedDict()
        for name, method in sorted(methods.iteritems(), key=lambda item: item[0]):
            api[name] = (_is_decorated(name), _argspec(name, method), _doc(method), )

        return self.render("api.html", instance=self._instance, api=api, version=str_version, theme=self._theme)


# ----------------------------------------------------------------------------------------------------------------------
#
# http rpc tornado application
#
# ----------------------------------------------------------------------------------------------------------------------
class TornadoRpcApplication(web.Application):
    def __init__(self, instance, handlers=None, default_host="", transforms=None, wsgi=False, theme='386', **settings):
        super(TornadoRpcApplication, self).__init__(handlers=handlers, default_host=default_host, transforms=transforms,
                                                    wsgi=wsgi, **settings)
        self._instance = instance
        self._theme = theme

    @property
    def instance(self):
        return self._instance

    @property
    def theme(self):
        return self._theme


# ----------------------------------------------------------------------------------------------------------------------
#
# single instance http rpc tornado server
#
# ----------------------------------------------------------------------------------------------------------------------
_RESERVED_ROUTES = ('/', '/rpc', '/ping')


class TornadoRpcServer(RpcServer):
    def __init__(self, address, instance, multiprocess=False, theme=None, handlers=None, debug=False,
                 xsrf_cookies=False, num_processes=0, *args, **kwargs):
        super(TornadoRpcServer, self).__init__(address, *args, **kwargs)
        settings = {
            'template_path': get_templates_dir(),
            'static_path': get_static_dir(),
            'xsrf_cookies': xsrf_cookies,
            'debug': debug
        }
        info('with debug          :%s', debug)
        info('with xsrf_cookies   :%s', xsrf_cookies)

        # add the extra handlers
        if not handlers:
            handlers = dict()
        if not isinstance(handlers, dict):
            raise ValueError('handlers must be None or a dict instance')

        if TornadoConfig.instance().use_body_streaming:
            _TornadoRequestHandler = TornadoStreamingRequestHandler
        else:
            _TornadoRequestHandler = TornadoRequestHandler

        app_handlers = [
            web.url(r"/", InstanceViewerHandler),
            web.url(r"/rpc", _TornadoRequestHandler),
            web.url(r"/ping", PingRequestHandler),
        ]
        for route, handler in handlers.iteritems():
            if route in _RESERVED_ROUTES:
                error('route %s already exists cannot override', route)
            else:
                app_handlers.append(web.url(route, handler))

        self._app = TornadoRpcApplication(instance, handlers=app_handlers, theme=theme, **settings)
        self._multiprocess = multiprocess
        self._sockets = bind_sockets(address[1], address=address[0])
        self._bound_address = self._sockets[0].getsockname()
        self._server = None
        self._num_processes = num_processes

    def server_forever(self, *args, **kwargs):
        try:
            if self._multiprocess:
                info('starting tornado server in multi-process mode')
                fork_processes(self._num_processes)
            else:
                info('starting tornado server in single-process mode')
            self._server = HTTPServer(self._app)
            self._server.add_sockets(self._sockets)
            IOLoop.instance().start()
        except Exception, e:
            error("exception in serve_forever: %s", e)
        finally:
            info('closing the server ...')
            self.stop()
            info('server shutdown complete')

    @property
    def bound_address(self):
        return self._bound_address

    def stop(self):
        super(TornadoRpcServer, self).stop()
        loop = IOLoop.instance()
        loop.add_callback(shutdown_tornado, loop, self._server)

# ----------------------------------------------------------------------------------------------------------------------
#
# Single instance Async manager based on the Tornado web server
#
# ----------------------------------------------------------------------------------------------------------------------
class TornadoManager(SingleInstanceAsyncManager):
    @property
    def _server_class(self):
        return TornadoRpcServer

    @property
    def _proxy_class(self):
        if self._async:
            return TornadoAsyncHttpRpcProxy
        return TornadoHttpRpcProxy
