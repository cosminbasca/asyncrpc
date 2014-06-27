__author__ = 'basca'


# class PreforkedManager(GeventManager):
# @classmethod
# def register(cls, instance, **kwargs):
#         if '_registry' not in cls.__dict__:
#             cls._registry = cls._registry.copy()
#
#         instance_id = hash(instance)
#         cls._registry[instance_id] = instance
#
#         return instance_id
#
#     @property
#     def _server_class(self):
#         return PreforkedRpcServer
#
#     def get_instance(self, instance_id):
#         if self._async:
#             if self._async_pooled:
#                 proxy = GeventPooledProxy(instance_id, self._bound_address, concurrency=self._pool_concurrency)
#             else:
#                 proxy = GeventProxy(instance_id, self._bound_address)
#         else:
#             proxy = InetProxy(instance_id, self._bound_address)
#         self._log.debug(
#             'created proxy "{0}" for instance id={1}'.format(type(proxy), instance_id))
#         return proxy



class PreforkedRpcClient(object):
    pass