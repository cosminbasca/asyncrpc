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
from abc import ABCMeta, abstractproperty
from collections import OrderedDict
from asyncrpc.exceptions import RpcServerNotStartedException
from asyncrpc.client import create, exposed_methods, AsyncSingleInstanceProxy, SingleInstanceProxy
from asyncrpc.process import BackgroundRunner
from asyncrpc.server import CherrypyWsgiRpcServer, TornadoWsgiRpcServer
from asyncrpc.log import debug, error, info, warn

__author__ = 'basca'


class BaseAsyncManager(object):
    __metaclass__ = ABCMeta


    def __init__(self, address=('127.0.0.1', 0), async=False, gevent_patch=False, retries=100, connection_timeout=10,
                 **kwargs):
        self._async = async
        self._connection_timeout = connection_timeout
        self._runner = BackgroundRunner(server_class=self._server_class, address=address, gevent_patch=gevent_patch,
                                        retries=retries)

    @abstractproperty
    def _server_class(self):
        return None

    @abstractproperty
    def _model(self):
        return None

    def __del__(self):
        self._runner.stop()

    def start(self, wait=True, theme=None, **kwargs):
        self._runner.start(wait, self._model, theme=theme, **kwargs)

    def stop(self):
        self._runner.stop()

    @property
    def bound_address(self):
        return self._runner.bound_address

# ----------------------------------------------------------------------------------------------------------------------
#
# Multi instance Async manager that supports gevent cooperative sockets. The server is threaded
#
# ----------------------------------------------------------------------------------------------------------------------
class AsyncManager(BaseAsyncManager):
    _registry = OrderedDict()

    @classmethod
    def register(cls, type_id, initialiser, with_private=False):
        if '_registry' not in cls.__dict__:
            cls._registry = cls._registry.copy()

        cls._registry[type_id] = initialiser
        slots = exposed_methods(initialiser, with_private=with_private).keys()

        def proxy_creator(self, *args, **kwargs):
            if not self._runner.is_running:
                raise RpcServerNotStartedException('the rcp server has not been started!')
            proxy = create(self.bound_address, type_id, slots, self._async, self._connection_timeout, *args, **kwargs)
            debug('created proxy %s for instance id: %s of typeid: %s', type(proxy), proxy.id, type_id)
            return proxy

        proxy_creator.__name__ = type_id
        setattr(cls, type_id, proxy_creator)

    def __del__(self):
        self._runner.stop()

    @property
    def _server_class(self):
        return CherrypyWsgiRpcServer

    @property
    def _model(self):
        return self._registry


# ----------------------------------------------------------------------------------------------------------------------
#
# Single instance Async manager that supports gevent cooperative sockets. The server is threaded
#
# ----------------------------------------------------------------------------------------------------------------------
class SingleInstanceAsyncManager(BaseAsyncManager):
    def __init__(self, instance, address=('127.0.0.1', 0), async=False, gevent_patch=False, retries=100,
                 connection_timeout=10, **kwargs):
        super(SingleInstanceAsyncManager, self).__init__(
            address=address, async=async, gevent_patch=gevent_patch, retries=retries,
            connection_timeout=connection_timeout, **kwargs)
        self._instance = instance

    @property
    def _server_class(self):
        return CherrypyWsgiRpcServer

    @property
    def _model(self):
        return self._instance

    @property
    def _proxy_class(self):
        if self._async:
            return AsyncSingleInstanceProxy
        return SingleInstanceProxy

    def proxy(self, slots=None, **kwargs):
        if not self._runner.is_running:
            raise RpcServerNotStartedException('the rcp server has not been started!')
        return self._proxy_class(self.bound_address, slots=slots, **kwargs)
