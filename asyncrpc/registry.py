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

