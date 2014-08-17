from collections import OrderedDict
from inspect import isclass, getmembers, isroutine

__author__ = 'basca'


class Registry(object):
    def __init__(self, **kwargs):
        self._data = OrderedDict()
        self._data.update(kwargs)

    def delete_instances(self):
        to_remove = [oid for oid, v in self._data.iteritems() if not isclass(v)]
        for oid in to_remove:
            del self._data[oid]

    def explained_instances(self):
        def _instance_members(obj):
            attributes = getmembers(obj, predicate=lambda a: not (isroutine(a)))
            return [attr for attr in attributes if not attr[0].startswith('__')]

        return [(oid, (type(instance), _instance_members(instance))) for oid, instance in self._data.iteritems()]

    def clear(self):
        self._data.clear()

    def get(self, instance_id, default=None):
        return self._data.get(instance_id, default)

    def set(self, instance_id, value):
        self._data[instance_id] = value

    def delete(self, instance_id):
        del self._data[instance_id]

    def has(self, instance_id):
        return instance_id in self._data

    def copy(self):
        return Registry(**self._data)

    @property
    def items_dict(self):
        return self._data

    def update(self, kwargs):
        self._data.update(kwargs)

