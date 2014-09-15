__author__ = 'basca'

from client import hidden, AsyncProxy, Proxy, SingleInstanceProxy, AsyncSingleInstanceProxy, create, dispatch, \
    ProxyFactory, RpcProxy, RegistryRpcProxy
from log import get_logger, set_level, logger
from manager import AsyncManager
from process import BackgroundRunner
from server import RpcServer, CherrypyWsgiRpcServer, TornadoWsgiRpcServer
from wsgi import RpcRegistryViewer, RpcRegistryMiddleware
from messaging import dumps, loads, register, registered_libs, select
from registry import Registry
from tornadorpc import TornadoManager, TornadoAsyncHttpRpcProxy, TornadoHttpRpcProxy
from util import format_address

set_level('critical', name='cherrypy.error')
set_level('critical', name='rdflib')