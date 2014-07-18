from pprint import pformat
from threading import RLock
import traceback
from asyncrpc.exceptions import CommandNotFoundException, InvalidInstanceId, current_error
from asyncrpc.log import get_logger
from msgpackutil import dumps, loads
from werkzeug.wrappers import Response, Request
from inspect import isclass

__author__ = 'basca'

# ----------------------------------------------------------------------------------------------------------------------
#
# Accepted commands on the registry
#
# ----------------------------------------------------------------------------------------------------------------------
class Commmand(object):
    NEW = '#NEW'
    RELASE = '#RELEASE'
    CLEAR = '#CLEAR'
    CLEAR_ALL = '#CLEAR_ALL'
    PING = '#PING'
    SHUTDOWN = '#SHUTDOWN'
    DEBUG = '#DEBUG'


# ----------------------------------------------------------------------------------------------------------------------
#
# WSGI RPC Registry Middleware - a wsgi app
#
# ----------------------------------------------------------------------------------------------------------------------
class RpcRegistryMiddleware(object):
    """
    wsgi application that handles rpc calls to multiple registered objects
    """

    def __init__(self, registry, shutdown_callback=None):
        if shutdown_callback and not hasattr(shutdown_callback, '__call__'):
            raise ValueError('shutdown_callback must be a callable instance')
        self._shutdown_callback = shutdown_callback

        self._registry = registry
        self._mutex = RLock()
        self._log = get_logger(self.__class__.__name__)

        self._handlers = {
            Commmand.NEW: self._handler_init,
            Commmand.RELASE: self._handler_release,
            Commmand.CLEAR: self._handler_clear,
            Commmand.CLEAR_ALL: self._handler_clear_all,
            Commmand.PING: self._handler_ping,
            Commmand.SHUTDOWN: self._handler_shutdown,
            Commmand.DEBUG: self._handler_debug,
        }

    def _handler_init(self, type_id, name, *args, **kwargs):
        try:
            self._mutex.acquire()
            _class = self._registry[type_id]
            instance = _class(*args, **kwargs)
            instance_id = hash(instance)
            self._registry[instance_id] = instance
            self._log.debug('got instance id:{0}'.format(instance_id))
            return instance_id
        finally:
            self._mutex.release()

    def _handler_release(self, instance_id, name, *args, **kwargs):
        if instance_id in self._registry:
            del self._registry[instance_id]
            return True
        return False

    def _handler_clear(self, instance_id, name, *args, **kwargs):
        to_remove = [oid for oid, v in self._registry.iteritems() if not isclass(v)]
        for oid in to_remove:
            del self._registry[oid]

    def _handler_clear_all(self, instance_id, name, *args, **kwargs):
        self._registry.iteritems.clear()

    def _handler_ping(self, instance_id, name, *args, **kwargs):
        return True

    def _handler_shutdown(self, instance_id, name, *args, **kwargs):
        if self._shutdown_callback:
            self._shutdown_callback()
        return True

    def _handler_debug(self, instance_id, name, *args, **kwargs):
        self._log.info('''
------------------------------------------------------------------------------------------------------------------------
REGISTRY:
{0}
------------------------------------------------------------------------------------------------------------------------
'''.format('\n'.join([
            '[{0}]\t{1} => {2}'.format(i, k, pformat(v)) for i, (k, v) in enumerate(self._registry.iteritems())])
        ))

    def _handle_rpc_call(self, instance_id, name, *args, **kwargs):
        instance = self._registry.get(instance_id, None)
        if not instance:
            raise InvalidInstanceId('insance with id:{0} not registered'.format(instance_id))
        func = getattr(instance, name, None)
        if not func:
            raise NameError('instance does not have method "{0}"'.format(name))
        return func(*args, **kwargs)


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
                result = self._handle_rpc_call(object_id, name, *args, **kwargs)
            error = None
        except Exception, e:
            error = current_error()
            result = None
            self._log.error('[_handle_request] error: {0}, traceback: \n{1}'.format(e, traceback.format_exc()))

        response = Response(dumps((result, error, )), mimetype='text/plain')
        return response(environ, start_response)

