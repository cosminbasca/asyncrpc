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
__author__ = 'basca'

from client import hidden, AsyncProxy, Proxy, SingleInstanceProxy, AsyncSingleInstanceProxy, create, dispatch, \
    ProxyFactory, RpcProxy, RegistryRpcProxy
from log import  set_logger_level, disable_logger, get_logger
from manager import AsyncManager
from process import BackgroundRunner
from server import RpcServer, CherrypyWsgiRpcServer, TornadoWsgiRpcServer
from wsgi import RpcRegistryViewer, RpcRegistryMiddleware
from messaging import dumps, loads, register, registered_libs, select
from registry import Registry
from tornadorpc import TornadoManager, TornadoAsyncHttpRpcProxy, TornadoHttpRpcProxy, TornadoConfig
from util import format_address, format_addresses

disable_logger('cherrypy.error')
disable_logger('rdflib')