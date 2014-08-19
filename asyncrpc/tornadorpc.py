import inspect
import os
import traceback
from tornado.concurrent import Future
from tornado.httpserver import HTTPServer
from tornado.netutil import bind_sockets
from tornado.template import Loader
from asyncrpc.__version__ import str_version
from asyncrpc.server import RpcServer
from asyncrpc.process import BackgroundRunner
from asyncrpc.exceptions import RpcServerNotStartedException, RpcRemoteException, handle_exception
from asyncrpc.messaging import loads, dumps
from asyncrpc.client import RpcProxy, exposed_methods
from asyncrpc.handler import RpcHandler
from asyncrpc.log import get_logger, set_level
from tornado.ioloop import IOLoop
from tornado.httpclient import AsyncHTTPClient, HTTPError, HTTPClient
from tornado import gen
from tornado import web
from docutils.core import publish_parts

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
        response = ('', None)
        try:
            response = http_client.fetch(self.url, body=message, method='POST',
                                         connect_timeout=300, request_timeout=300)
        except HTTPError as e:
            self._log.error("HTTP Error: {0}".format(e))
            handle_exception({'message': e.message, 'type': e.__class__.__name__, 'traceback': traceback.format_exc(),
                              'address': self.url})
        finally:
            http_client.close()
        return response


# ----------------------------------------------------------------------------------------------------------------------
#
# asynchronous decorator alias
#
# ----------------------------------------------------------------------------------------------------------------------
asynchronous = gen.coroutine

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
        response = ('', None)
        try:
            response = yield http_client.fetch(self.url, body=message, method='POST', connect_timeout=300,
                                               request_timeout=300)
        except HTTPError as e:
            self._log.error("HTTP Error: {0}".format(e))
            handle_exception({'message': e.message, 'type': e.__class__.__name__, 'traceback': traceback.format_exc(),
                              'address': self.url})
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
            error = {'message': e.message, 'type': e.__class__.__name__, 'traceback': traceback.format_exc(),
                     'address': '{0}://{1}'.format(self.request.protocol, self.request.host)}
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
                return publish_parts(docstring, writer_name='html')['fragment']
            return '&nbsp;'

        api = {
            name: (_is_decorated(name), _argspec(name, method), _doc(method), )
            for name, method in methods.iteritems()
        }
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
class TornadoRpcServer(RpcServer):
    def __init__(self, address, instance, multiprocess=False, theme=None, *args, **kwargs):
        super(TornadoRpcServer, self).__init__(address, *args, **kwargs)
        settings = {'template_path': os.path.join(os.path.dirname(__file__), 'templates'),
                    'static_path': os.path.join(os.path.dirname(__file__), 'static'),
                    # 'xsrf_cookies': True,
        }
        app = TornadoRpcApplication(instance, handlers=[
            web.url(r"/", InstanceViewerHandler),
            web.url(r"/rpc", TornadoRequestHandler),
            web.url(r"/ping", PingRequestHandler),
        ], theme=theme, **settings)
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
        IOLoop.instance().stop()  # stop the tornado IO loop
        super(TornadoRpcServer, self).stop()


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

