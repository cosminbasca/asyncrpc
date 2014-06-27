from geventmanager.manager import GeventManager
from geventmanager.server import PreforkedRpcServer

__author__ = 'basca'


class PreforkedManager(GeventManager):
    @classmethod
    def register(cls, instance, **kwargs):
        if '_registry' not in cls.__dict__:
            cls._registry = cls._registry.copy()

        instance_id = hash(instance)
        cls._registry[instance_id] = instance

        return instance_id

    @property
    def _server_class(self):
        return PreforkedRpcServer

    def __init__(self, instance, slots=None, address=None, async=False, async_pooled=False, gevent_patch=False,
                 pool_concurrency=32, retries=2000):
        self._instance = instance
        self._slots = slots
        if not isinstance(slots, (list, tuple, set)):
            raise ValueError('slots must be a list/tuple or set or method names')
        for slot in self._slots:
            member = getattr(self._instance, slot, None)
            if not hasattr(member, '__call__'):
                raise ValueError('slot "{0}" not callable for {1}'.format(slot, self._instance))
        super(PreforkedManager, self).__init__(address=address, async=async, async_pooled=async_pooled,
                                               gevent_patch=gevent_patch, pool_concurrency=pool_concurrency,
                                               retries=retries)

    def get_instance(self, instance_id):
        proxy = self._proxy(instance_id)
        self._log.debug(
            'created proxy "{0}" for instance id={1}'.format(type(proxy), instance_id))
        return proxy
