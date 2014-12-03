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

