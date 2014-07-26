from abc import ABCMeta, abstractmethod

__author__ = 'basca'

class RpcHandler(object):
    __metaclass__ = ABCMeta

    @abstractmethod
    def get_instance(self, *args, **kwargs):
        return None

    def rpc(self, *args, **kwargs):
        instance = self.get_instance(*args, **kwargs)
        def rpc_call(name, *args, **kwargs):
            func = getattr(instance, name, None)
            if not func:
                raise NameError('instance does not have method "{0}"'.format(name))
            return func(*args, **kwargs)
        return rpc_call

