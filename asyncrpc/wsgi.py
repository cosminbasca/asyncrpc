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
import traceback
from threading import RLock
from collections import OrderedDict
from werkzeug.wsgi import SharedDataMiddleware
from asyncrpc.commands import Command
from asyncrpc.exceptions import CommandNotFoundException, InvalidInstanceId, InvalidTypeId, ErrorMessage
from asyncrpc.handler import RpcHandler
from asyncrpc.__version__ import str_version
from asyncrpc.messaging import dumps, loads
from asyncrpc.registry import Registry
from asyncrpc.log import debug, warn, info, error
from werkzeug.wrappers import Response, Request
from inspect import isclass
from jinja2 import Environment, FileSystemLoader
from asyncrpc.util import get_templates_dir, get_static_dir

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
    def __init__(self, types_registry, registry, with_static=True, theme='386'):
        if not isinstance(types_registry, (dict, OrderedDict)):
            raise ValueError('types_registry must be a dict or an OrderedDict')
        if not isinstance(registry, Registry):
            raise ValueError('registry must be a Registry')

        self._types_registry = types_registry
        self._registry = registry
        self._with_static = with_static
        self._theme = theme
        self._jinja_env = Environment(loader=FileSystemLoader(get_templates_dir()), autoescape=True)

    def render_template(self, template, **params):
        t = self._jinja_env.get_template(template)
        return t.render(params)

    def registry_wsgi_app(self, environ, start_response):
        request = Request(environ)
        if 'clearAll' in request.args.keys():
            self._registry.delete_instances()
        response = Response(self.render_template('registry.html', version=str_version, classes=self._types_registry,
                                                 instances=self._registry.explained_instances(),
                                                 isclass=isclass, theme=self._theme), mimetype='text/html')
        return response(environ, start_response)

    def __call__(self, environ, start_response):
        app = self.registry_wsgi_app
        if self._with_static:
            app = SharedDataMiddleware(app, {
                '/static': get_static_dir()
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

    def __init__(self, types_registry, registry):
        if not isinstance(types_registry, (dict, OrderedDict)):
            raise ValueError('types_registry must be a dict or an OrderedDict')
        if not isinstance(registry, Registry):
            raise ValueError('registry must be a Registry')

        self._types_registry = types_registry
        self._registry = registry
        self._mutex = RLock()

        self._handlers = {
            Command.NEW: self._handler_new,
            Command.RELEASE: self._handler_release,
            Command.CLEAR: self._handler_clear,
            Command.CLEAR_ALL: self._handler_clear_all,
        }

    def _handler_new(self, type_id, name, *args, **kwargs):
        try:
            self._mutex.acquire()
            _class = self._types_registry.get(type_id, None)
            if not _class:
                raise InvalidTypeId('could not find {0} in registry, instance could not be created'.format(type_id))
            instance = _class(*args, **kwargs)
            instance_id = hash(instance)
            self._registry.set(instance_id, instance)
            debug('got instance ID:%s', instance_id)
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
        debug('access ID:%s', instance_id)
        instance = self._registry.get(instance_id, None)
        if not instance:
            raise InvalidInstanceId('instance with id:{0} not registered'.format(instance_id))
        return instance

    def __call__(self, environ, start_response):
        request = Request(environ)
        try:
            object_id, name, args, kwargs = loads(request.get_data(cache=True))
            if name.startswith('#'):
                command_handler = self._handlers.get(name, None)
                if command_handler:
                    debug('command: "%s"', name[1:])
                    result = command_handler(object_id, name, *args, **kwargs)
                else:
                    error('command "%s" not found', name)
                    raise CommandNotFoundException('command {0} not defined'.format(name[1:]))
            else:
                debug('calling function: "%s"', name)
                result = self.rpc(object_id)(name, *args, **kwargs)
            execution_error = None
        except Exception, e:
            execution_error = ErrorMessage.from_exception(e, address=request.host_url)
            result = None
            error('error: %s, traceback: \n%s', e, traceback.format_exc())

        response = Response(dumps((result, execution_error, )), mimetype='text/plain')
        return response(environ, start_response)

