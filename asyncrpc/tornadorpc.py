from abc import ABCMeta
from collections import OrderedDict
import inspect
import traceback
from tornado.concurrent import Future
from tornado.httpserver import HTTPServer
from tornado.netutil import bind_sockets
from tornado.process import fork_processes
from asyncrpc.__version__ import str_version
from asyncrpc.server import RpcServer, shutdown_tornado
from asyncrpc.process import BackgroundRunner
from asyncrpc.exceptions import RpcServerNotStartedException, handle_exception, ErrorMessage
from asyncrpc.messaging import loads, dumps
from asyncrpc.client import RpcProxy, exposed_methods, SingleCastHTTPTransport, MultiCastHTTPTransport
from asyncrpc.handler import RpcHandler
from asyncrpc.util import get_templates_dir, get_static_dir
from asyncrpc.log import debug, info, warn, error
from tornado.ioloop import IOLoop
from tornado.httpclient import AsyncHTTPClient, HTTPError, HTTPClient
from tornado import gen
from tornado import web
from docutils.core import publish_parts

__author__ = 'basca'


class TornadoConfig(object):
    def __init__(self):
        self._use_curl = False
        self._force_instance = True

    @property
    def use_curl(self):
        return self._use_curl

    @use_curl.setter
    def use_curl(self, value):
        self._use_curl = value
        if self._use_curl:
            try:
                AsyncHTTPClient.configure("tornado.curl_httpclient.CurlAsyncHTTPClient")
            except ImportError, err:
                self._use_curl = False
                warn('could not configure Tornado Web to use cURL. Reason: %s', err)
        else:
            AsyncHTTPClient.configure("tornado.httpclient.AsyncHTTPClient")

    @property
    def force_instance(self):
        return self._force_instance

    @force_instance.setter
    def force_instance(self, value):
        self._force_instance = value

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
    def __init__(self, address, connection_timeout):
        super(SynchronousTornadoHTTP, self).__init__(address, connection_timeout)

    def __call__(self, message):
        http_client = HTTPClient()
        response = ('', None)
        try:
            response = http_client.fetch(self.url, body=message, method='POST',
                                         connect_timeout=self.connection_timeout,
                                         request_timeout=self.connection_timeout)
        except HTTPError as e:
            error("HTTP Error: %s", e)
            handle_exception(ErrorMessage.from_exception(e, address=self.url))
        finally:
            http_client.close()
        return response

    def content(self, response):
        return response.body

    def status_code(self, response):
        return response.code


class AsynchronousTornadoHTTP(SingleCastHTTPTransport):
    def __init__(self, address, connection_timeout):
        super(AsynchronousTornadoHTTP, self).__init__(address, connection_timeout)
        self._force_instance = TornadoConfig.instance().force_instance

    @gen.coroutine
    def __call__(self, message):
        http_client = AsyncHTTPClient(force_instance=self._force_instance)
        response = ('', None)
        try:
            response = yield http_client.fetch(self.url, body=message, method='POST',
                                               connect_timeout=self.connection_timeout,
                                               request_timeout=self.connection_timeout)
        except HTTPError as e:
            error("HTTP Error: %s", e)
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
        self._force_instance = TornadoConfig.instance().force_instance

    @gen.coroutine
    def __call__(self, message):
        clients = [( AsyncHTTPClient(force_instance=self._force_instance), url ) for url in self.urls]
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
DEFAULT_TORNADO_CONNECTION_TIMEOUT = 300


class TornadoHttpRpcProxy(RpcProxy):
    def __init__(self, address, slots=None, connection_timeout=DEFAULT_TORNADO_CONNECTION_TIMEOUT):
        super(TornadoHttpRpcProxy, self).__init__(address, slots=slots, connection_timeout=connection_timeout)

    def get_transport(self, address, connection_timeout):
        return SynchronousTornadoHTTP(address, connection_timeout)


# ----------------------------------------------------------------------------------------------------------------------
#
# asynchronous tornado http rpc proxy
#
# ----------------------------------------------------------------------------------------------------------------------
class TornadoAsyncHttpRpcProxy(RpcProxy):
    def __init__(self, address, slots=None, connection_timeout=DEFAULT_TORNADO_CONNECTION_TIMEOUT):
        super(TornadoAsyncHttpRpcProxy, self).__init__(
            address, slots=slots, connection_timeout=connection_timeout)

    def get_transport(self, address, connection_timeout):
        if isinstance(address, (list, set)):
            return MulticastAsynchronousTornadoHTTP(address, connection_timeout)
        return AsynchronousTornadoHTTP(address, connection_timeout)

    @gen.coroutine
    def _rpc_call(self, name, *args, **kwargs):
        debug('calling "%s"', name)
        response = yield self._transport(self._message(name, *args, **kwargs))
        result = self._process_response(response)
        raise gen.Return(result)


def async_call(address):
    """
    create and perform an asynchronous HTTP RPC call to a tornado (single instance) RPC server
    :param address: a (host,port) tuple or "ip:port" string
    :return: a tornado Future of the RPC response (or an error otherwise)
    """
    return TornadoAsyncHttpRpcProxy(address)


def call(address):
    """
    create and perform a synchronous HTTP RPC call to a tornado (single instance) RCP server
    :param address: a (host,port) tuple or "ip:port" string
    :return: the actual RPC response (or an error otherwise)
    """
    return TornadoHttpRpcProxy(address)


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
                 xsrf_cookies=False, *args, **kwargs):
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

        app_handlers = [
            web.url(r"/", InstanceViewerHandler),
            web.url(r"/rpc", TornadoRequestHandler),
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

    def server_forever(self, *args, **kwargs):
        try:
            if self._multiprocess:
                info('starting tornado server in multi-process mode')
                fork_processes(0)
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


class TornadoManager(object):
    def __init__(self, instance, address=('127.0.0.1', 0), async=False, gevent_patch=False, retries=100, **kwargs):
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

    def start(self, wait=True, multiprocess=False, theme=None, **kwargs):
        self._runner.start(wait, self._instance, multiprocess=multiprocess, theme=theme, **kwargs)

    def stop(self):
        self._runner.stop()

    @property
    def bound_address(self):
        return self._runner.bound_address
