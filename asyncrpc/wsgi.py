import os
from threading import RLock
import traceback
from werkzeug.wsgi import SharedDataMiddleware
from asyncrpc.commands import Command
from asyncrpc.exceptions import CommandNotFoundException, InvalidInstanceId, current_error
from asyncrpc.handler import RpcHandler
from asyncrpc.log import get_logger
from asyncrpc.__version__ import str_version
from asyncrpc.messaging import dumps, loads
from werkzeug.wrappers import Response, Request
from inspect import isclass
from jinja2 import Environment, FileSystemLoader
from asyncrpc.registry import Registry

__author__ = 'basca'


# ----------------------------------------------------------------------------------------------------------------------
#
# WSGI simple ping middleware
#
# ----------------------------------------------------------------------------------------------------------------------
def ping_middleware(environ, start_response):
    response = Response("pong", mimetype='text/plain')
    return response(environ, start_response)

# ----------------------------------------------------------------------------------------------------------------------
#
# WSGI RPC Registry viewer - a wsgi app
#
# ----------------------------------------------------------------------------------------------------------------------
class RpcRegistryViewer(object):
    def __init__(self, registry, with_static=True, theme='386'):
        if not isinstance(registry, Registry):
            raise ValueError('registry must be a Registry')
        self._registry = registry
        self._with_static = with_static
        self._theme = theme
        template_dir = os.path.join(os.path.dirname(__file__), 'templates')
        self._jinja_env = Environment(loader=FileSystemLoader(template_dir), autoescape=True)

    def render_template(self, template, **params):
        t = self._jinja_env.get_template(template)
        return t.render(params)

    def registry_wsgi_app(self, environ, start_response):
        request = Request(environ)
        if 'clearAll' in request.args.keys():
            self._registry.delete_instances()
        response = Response(self.render_template('registry.html', version=str_version,
                                 registry_items=self._registry.explained_instances(),
                                 isclass=isclass, theme=self._theme), mimetype='text/html')
        return response(environ, start_response)

    def __call__(self, environ, start_response):
        app = self.registry_wsgi_app
        if self._with_static:
            app = SharedDataMiddleware(app, {
                '/static': os.path.join(os.path.dirname(__file__), 'static')
            })
        return app(environ, start_response)


# ----------------------------------------------------------------------------------------------------------------------
#
# WSGI RPC Registry Middleware - a wsgi app
#
# ----------------------------------------------------------------------------------------------------------------------
class RpcRegistryMiddleware(RpcHandler):
    """
    wsgi application that handles rpc calls to multiple registered objects
    """

    def __init__(self, registry):
        if not isinstance(registry, Registry):
            raise ValueError('registry must be a Registry')

        self._registry = registry
        self._mutex = RLock()
        self._log = get_logger(self.__class__.__name__)

        self._handlers = {
            Command.NEW: self._handler_init,
            Command.RELEASE: self._handler_release,
            Command.CLEAR: self._handler_clear,
            Command.CLEAR_ALL: self._handler_clear_all,
        }

    def _handler_init(self, type_id, name, *args, **kwargs):
        try:
            self._mutex.acquire()
            _class = self._registry.get(type_id)
            instance = _class(*args, **kwargs)
            instance_id = hash(instance)
            self._registry.set(instance_id, instance)
            self._log.debug('got instance id:{0}'.format(instance_id))
            return instance_id
        finally:
            self._mutex.release()

    def _handler_release(self, instance_id, name, *args, **kwargs):
        if self._registry.has(instance_id):
            self._registry.delete(instance_id)
            return True
        return False

    def _handler_clear(self, instance_id, name, *args, **kwargs):
        self._registry.delete_instances()

    def _handler_clear_all(self, instance_id, name, *args, **kwargs):
        self._registry.clear()

    def get_instance(self, instance_id):
        self._log.debug('ACCESS ID {0}'.format(instance_id))
        instance = self._registry.get(instance_id, None)
        if not instance:
            raise InvalidInstanceId('instance with id:{0} not registered'.format(instance_id))
        return instance

    def __call__(self, environ, start_response):
        try:
            request = Request(environ)
            object_id, name, args, kwargs = loads(request.get_data(cache=True))
            if name.startswith('#'):
                command_handler = self._handlers.get(name, None)
                if command_handler:
                    self._log.info('command: "{0}"'.format(name[1:]))
                    result = command_handler(object_id, name, *args, **kwargs)
                else:
                    self._log.error('command "{0}" not found'.format(name))
                    raise CommandNotFoundException('command {0} not defined'.format(name[1:]))
            else:
                self._log.debug('calling function: "{0}"'.format(name))
                result = self.rpc(object_id)(name, *args, **kwargs)
            error = None
        except Exception, e:
            error = current_error()
            result = None
            self._log.error('error: {0}, traceback: \n{1}'.format(e, traceback.format_exc()))

        response = Response(dumps((result, error, )), mimetype='text/plain')
        return response(environ, start_response)

