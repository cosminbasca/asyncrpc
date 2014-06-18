from abc import ABCMeta, abstractmethod, abstractproperty
import cPickle

__author__ = 'basca'

_DATA = 'd'
_OID = '__oid__'

cPickle_dumps = cPickle.dumps
cPickle_loads = cPickle.loads

# ----------------------------------------------------------------------------------------------------------------------
#
# the hook abc
#
# ----------------------------------------------------------------------------------------------------------------------
class Hook(object):
    __metaclass__ = ABCMeta

    @abstractproperty
    def type(self):
        pass

    @abstractmethod
    def reduce(self, value):
        pass

    @abstractmethod
    def create(self, value_dict):
        pass


class DefaultHook(Hook):
    def type(self):
        return object


    def reduce(self, value):
        return {_DATA: cPickle_dumps(value)}


    def create(self, value_dict):
        return cPickle_loads(value_dict[_DATA])


# ----------------------------------------------------------------------------------------------------------------------
#
# the registry abc & Hooks registry
#
# ----------------------------------------------------------------------------------------------------------------------
# noinspection PyBroadException
class HooksRegistry(object):
    _id2hook = dict()
    _type2hook = dict()
    _default = DefaultHook()

    @classmethod
    def instance(cls):
        if not hasattr(cls, "_instance"):
            cls._instance = cls()
        return cls._instance

    def __getitem__(self, hook_id):
        if isinstance(hook_id, (long, int)):
            return self._id2hook[hook_id]
        return self._type2hook[hook_id]

    def register(self, hook_id, hook_class):
        if hook_id in self._id2hook:
            raise ValueError('item_id already registered for {0}'.format(self._id2hook[hook_id]))
        if not issubclass(hook_class, Hook):
            raise ValueError('item_class not a subclass of Hook')
        hook = hook_class()
        self._id2hook[hook_id] = hook
        self._type2hook[hook.type] = (hook_id, hook)


    def pack(self, value):
        try:
            hook_id, hook = self._type2hook[type(value)]
        except:
            hook_id, hook = (0, self._default)
        value_dict = hook.reduce(value)
        value_dict[_OID] = hook_id
        return value_dict


    def unpack(self, value_dict):
        if _OID in value_dict:
            hook_id = value_dict[_OID]
            try:
                return self._id2hook[hook_id].create(value_dict)
            except:
                return self._default.create(value_dict)
        return value_dict


HOOKS = HooksRegistry.instance()
