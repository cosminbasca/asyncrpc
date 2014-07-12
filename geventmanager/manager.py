from geventmanager.server import PreforkedRpcServer, ThreadedRpcServer, DefaultThreadedRpcServer, BackgroundServerRunner
from geventmanager.proxy import InetProxy, GeventProxy, GeventPooledProxy, Dispatcher
from geventmanager.exceptions import RpcServerNotStartedException
from geventmanager.log import get_logger
from collections import OrderedDict

__author__ = 'basca'

__all__ = ['GeventManager', 'PreforkedSingletonManager']

# ----------------------------------------------------------------------------------------------------------------------
#
# a generic manager, that supports gevent cooperative sockets as well. The server is threaded
#
# ----------------------------------------------------------------------------------------------------------------------
class GeventManager(object):
    _registry = OrderedDict()

    @classmethod
    def register(cls, type_id, initialiser, slots=None):
        if '_registry' not in cls.__dict__:
            cls._registry = cls._registry.copy()

        cls._registry[type_id] = initialiser

        def proxy_creator(self, *args, **kwargs):
            if not self._runner.is_running:
                raise RpcServerNotStartedException('the rcp server has not been started!')

            _init = Dispatcher(self.bound_address, type_id=type_id)
            instance_id = _init('#INIT', *args, **kwargs)
            proxy = self._proxy(instance_id, slots=slots)
            self._log.debug(
                'created proxy "{0}" for instance id={1} of type {2}'.format(type(proxy), instance_id, type_id))
            return proxy

        proxy_creator.__name__ = type_id
        setattr(cls, type_id, proxy_creator)

    def _proxy(self, instance_id, slots=None):
        if self._async:
            if self._async_pooled:
                return GeventPooledProxy(instance_id, self.bound_address, concurrency=self._pool_concurrency,
                                         slots=slots)
            else:
                return GeventProxy(instance_id, self.bound_address, slots=slots)
        else:
            return InetProxy(instance_id, self.bound_address, slots=slots)

    def __init__(self, address=None, async=False, async_pooled=False, gevent_patch=False, pool_concurrency=32,
                 retries=2000, **kwargs):
        self._log = get_logger(self.__class__.__name__)

        self._async = async
        self._async_pooled = async_pooled
        self._pool_concurrency = pool_concurrency

        self._runner = BackgroundServerRunner(server_class=self._server_class, address=address,
                                              registry=self._registry, gevent_patch=gevent_patch, retries=retries)

    def __del__(self):
        self._runner.stop()

    @property
    def _server_class(self):
        return ThreadedRpcServer
        # return DefaultThreadedRpcServer

    def start(self, wait=True, **kwargs):
        self._runner.start(wait=wait, **kwargs)

    def stop(self):
        self._runner.stop()

    def debug(self):
        if self._runner.is_running:
            self._runner.dispatch('#DEBUG')

    @property
    def bound_address(self):
        return self._runner.bound_address


# ----------------------------------------------------------------------------------------------------------------------
#
# a single instance preforked RPC manager.
#
# ----------------------------------------------------------------------------------------------------------------------
class PreforkedSingletonManager(GeventManager):
    @classmethod
    def register(cls, type_id, initialiser, slots=None):
        raise NotImplementedError

    @property
    def _server_class(self):
        return PreforkedRpcServer

    def __init__(self, instance, slots=None, address=None, async=False, async_pooled=False, gevent_patch=False,
                 pool_concurrency=32, retries=2000):
        self._registry[0] = instance
        self._slots = slots

        if not isinstance(slots, (list, tuple, set)):
            raise ValueError('slots must be a list/tuple or set or method names')
        for slot in self._slots:
            member = getattr(instance, slot, None)
            if not hasattr(member, '__call__'):
                raise ValueError('slot "{0}" not callable for {1}'.format(slot, instance))
        super(PreforkedSingletonManager, self).__init__(address=address, async=async, async_pooled=async_pooled,
                                                        gevent_patch=gevent_patch, pool_concurrency=pool_concurrency,
                                                        retries=retries)
        self._instance_proxy = None

    @property
    def proxy(self):
        if not self._instance_proxy:
            self._instance_proxy = self._proxy(0, slots=self._slots)
            self._log.debug('created proxy "{0}"'.format(type(self._instance_proxy)))
        return self._instance_proxy
