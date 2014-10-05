from collections import OrderedDict
import inspect
import os
import traceback
from tornado.concurrent import Future
from tornado.httpserver import HTTPServer
from tornado.netutil import bind_sockets
from asyncrpc.__version__ import str_version
from asyncrpc.server import RpcServer, shutdown_tornado
from asyncrpc.process import BackgroundRunner
from asyncrpc.exceptions import RpcServerNotStartedException, handle_exception, ErrorMessage
from asyncrpc.messaging import loads, dumps
from asyncrpc.client import RpcProxy, exposed_methods, HTTPTransport
from asyncrpc.handler import RpcHandler
from asyncrpc.log import get_logger
from tornado.ioloop import IOLoop
from tornado.httpclient import AsyncHTTPClient, HTTPError, HTTPClient
from tornado import gen
from tornado import web
from tornado.process import task_id
from docutils.core import publish_parts
from asyncrpc.wsgi import get_templates_dir, get_static_dir

__author__ = 'basca'

# USE_CURL = True
USE_CURL = False
if USE_CURL:
    try:
        from tornado.curl_httpclient import CurlAsyncHTTPClient

        AsyncHTTPClient.configure(CurlAsyncHTTPClient)
    except ImportError:
        pass

ASYNC_HTTP_FORCE_INSTANCE = True

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
class SynchronousTornadoHTTP(HTTPTransport):
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
            self._log.error("HTTP Error: {0}".format(e))
            handle_exception(ErrorMessage.from_exception(e, address=self.url))
        finally:
            http_client.close()
        return response

    def content(self, response):
        return response.body

    def status_code(self, response):
        return response.code


class AsynchronousTornadoHTTP(HTTPTransport):
    def __init__(self, address, connection_timeout):
        super(AsynchronousTornadoHTTP, self).__init__(address, connection_timeout)

    @gen.coroutine
    def __call__(self, message):
        http_client = AsyncHTTPClient(force_instance=ASYNC_HTTP_FORCE_INSTANCE)
        response = ('', None)
        try:
            response = yield http_client.fetch(self.url, body=message, method='POST',
                                               connect_timeout=self.connection_timeout,
                                               request_timeout=self.connection_timeout)
        except HTTPError as e:
            self._log.error("HTTP Error: {0}".format(e))
            handle_exception(ErrorMessage.from_exception(e, address=self.url))
        finally:
            if ASYNC_HTTP_FORCE_INSTANCE:
                http_client.close()
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
    def __init__(self, address, slots=None, connection_timeout=DEFAULT_TORNADO_CONNECTION_TIMEOUT, **kwargs):
        super(TornadoHttpRpcProxy, self).__init__(address, slots=slots, connection_timeout=connection_timeout, **kwargs)

    def get_transport(self, address, connection_timeout):
        return SynchronousTornadoHTTP(address, connection_timeout)


# ----------------------------------------------------------------------------------------------------------------------
#
# asynchronous tornado http rpc proxy
#
# ----------------------------------------------------------------------------------------------------------------------
class TornadoAsyncHttpRpcProxy(RpcProxy):
    def __init__(self, address, slots=None, connection_timeout=DEFAULT_TORNADO_CONNECTION_TIMEOUT, **kwargs):
        super(TornadoAsyncHttpRpcProxy, self).__init__(address, slots=slots, connection_timeout=connection_timeout,
                                                       **kwargs)

    def get_transport(self, address, connection_timeout):
        return AsynchronousTornadoHTTP(address, connection_timeout)

    @gen.coroutine
    def _rpc_call(self, name, *args, **kwargs):
        self._log.debug("calling {0}".format(name))
        response = yield self._transport(self._message(name, *args, **kwargs))
        raise gen.Return(self._get_result(response))


def async_call(address):
    """
    create and perform an asynchronous HTTP RPC call to a tornado (single instance) RPC server
    :param address: a (host,port) tuple
    :return: a tornado Future of the RPC response (or an error otherwise)
    """
    return TornadoAsyncHttpRpcProxy(tuple(address) if isinstance(address, list) else address)


def call(address):
    """
    create and perform a synchronous HTTP RPC call to a tornado (single instance) RCP server
    :param address: a (host,port) tuple
    :return: the actual RPC response (or an error otherwise)
    """
    return TornadoHttpRpcProxy(tuple(address) if isinstance(address, list) else address)


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
        self._log = get_logger(owner=self)

    def get_instance(self, *args, **kwargs):
        return self._instance

    @gen.coroutine
    def post(self, *args, **kwargs):
        try:
            name, args, kwargs = loads(self.request.body)
            self._log.debug('calling function: "{0}"'.format(name))
            result = self.rpc()(name, *args, **kwargs)
            if isinstance(result, Future):
                result = yield result
            error = None
        except Exception, e:
            error = ErrorMessage.from_exception(e, address='{0}://{1}'.format(self.request.protocol, self.request.host))
            result = None
            self._log.error('error: {0}, traceback: \n{1}'.format(e, traceback.format_exc()))
        response = dumps((result, error))
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


class InstanceViewerHandler(web.RequestHandler):
    def __init__(self, application, request, **kwargs):
        super(InstanceViewerHandler, self).__init__(application, request, **kwargs)
        if not isinstance(application, TornadoRpcApplication):
            raise ValueError('application must be an instance of TornadoRpcApplication')
        self._instance = application.instance
        self._theme = application.theme

    def get(self, *args, **kwargs):
        async_methods = set(decorated_nethods(self._instance.__class__, "asynchronous", "gen.coroutine"))
        methods = exposed_methods(self._instance, with_private=False)

        def _is_decorated(name):
            return name in async_methods

        def _argspec(name, method):
            if _is_decorated(name):
                original = method.func_closure[0].cell_contents
                spec = inspect.getargspec(original)
            else:
                spec = inspect.getargspec(method)
            spec = spec._asdict()
            if spec['defaults']:
                r_defaults = list(reversed(spec['defaults']))
                r_args = list(reversed(spec['args']))
                spec['defaults'] = list(reversed([(r_args[i], val) for i, val in enumerate(r_defaults)]))
            return spec

        def _doc(method):
            docstring = inspect.getdoc(method)
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
        self._log.info('with debug          :%s', debug)
        self._log.info('with xsrf_cookies   :%s', xsrf_cookies)

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
                self._log.error('route %s already exists cannot override', route)
            else:
                app_handlers.append(web.url(route, handler))

        app = TornadoRpcApplication(instance, handlers=app_handlers, theme=theme, **settings)
        self._multiprocess = multiprocess
        self._server = HTTPServer(app)
        self._sockets = bind_sockets(address[1], address=address[0])
        if not self._multiprocess:
            self._server.add_sockets(self._sockets)
        self._bound_address = self._sockets[0].getsockname()

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
            self.stop()
            self._log.info('server shutdown complete')

    @property
    def bound_address(self):
        return self._bound_address

    def stop(self):
        super(TornadoRpcServer, self).stop()
        loop = IOLoop.instance()
        loop.add_callback(shutdown_tornado, loop, self._server)


class TornadoManager(object):
    def __init__(self, instance, address=('127.0.0.1', 0), async=False, gevent_patch=False, retries=100, **kwargs):
        self._log = get_logger(owner=self)
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

