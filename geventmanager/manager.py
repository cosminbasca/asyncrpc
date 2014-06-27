from collections import OrderedDict
from geventmanager.log import get_logger
from geventmanager.proxy import InetProxy, GeventProxy, GeventPooledProxy, Dispatcher
from geventmanager.server import PreforkedRpcServer, ThreadedRpcServer, BackgroundServerRunner
from geventmanager.exceptions import RpcServerNotStartedException


__author__ = 'basca'

__all__ = ['RpcManager', 'GeventManager']

# ----------------------------------------------------------------------------------------------------------------------
#
# a generic manager, that supports gevent cooperative sockets as well. The server is threaded
#
# ----------------------------------------------------------------------------------------------------------------------
class GeventManager(object):
    _registry = OrderedDict()

    @classmethod
    def register(cls, type_id, initialiser):
        if '_registry' not in cls.__dict__:
            cls._registry = cls._registry.copy()

        cls._registry[type_id] = initialiser

        def proxy_creator(self, *args, **kwargs):
            if not self._runner.is_running:
                raise RpcServerNotStartedException('the rcp server has not been started!')

            _init = Dispatcher(self.bound_address, type_id=type_id)
            instance_id = _init('#INIT', *args, **kwargs)
            if self._async:
                if self._async_pooled:
                    proxy = GeventPooledProxy(instance_id, self.bound_address, concurrency=self._pool_concurrency)
                else:
                    proxy = GeventProxy(instance_id, self.bound_address)
            else:
                proxy = InetProxy(instance_id, self.bound_address)
            self._log.debug(
                'created proxy "{0}" for instance id={1} of type {2}'.format(type(proxy), instance_id, type_id))
            return proxy

        proxy_creator.__name__ = type_id
        setattr(cls, type_id, proxy_creator)

    def __init__(self, address=None, async=False, async_pooled=False, gevent_patch=False, pool_concurrency=32,
                 retries=2000, **kwargs):
        self._log = get_logger(self.__class__.__name__)

        self._async = async
        self._async_pooled = async_pooled
        self._pool_concurrency = pool_concurrency

        self._runner = BackgroundServerRunner(server_class=self._server_class, address=address,
                                              registry=self._registry, gevent_patch=gevent_patch, retries=retries)

    @property
    def _server_class(self):
        return ThreadedRpcServer

    def start(self, wait=True):
        self._runner.start(wait=wait)

    def debug(self):
        if self._runner.is_running:
            self._runner.dispatch('#DEBUG')

    @property
    def bound_address(self):
        return self._runner.bound_address
