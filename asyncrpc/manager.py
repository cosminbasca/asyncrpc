from asyncrpc.exceptions import RpcServerNotStartedException
from asyncrpc.log import get_logger
from asyncrpc.client import dispatch, create, exposed_methods
from asyncrpc.wsgi import Command
from asyncrpc.process import BackgroundRunner
from asyncrpc.server import CherrypyRpcServer, TornadoRpcServer
from collections import OrderedDict

__author__ = 'basca'

# ----------------------------------------------------------------------------------------------------------------------
#
# a generic manager, that supports gevent cooperative sockets as well. The server is threaded
#
# ----------------------------------------------------------------------------------------------------------------------
class AsyncManager(object):
    _registry = OrderedDict()

    @classmethod
    def register(cls, type_id, initialiser):
        if '_registry' not in cls.__dict__:
            cls._registry = cls._registry.copy()

        cls._registry[type_id] = initialiser
        slots = exposed_methods(initialiser).keys()

        def proxy_creator(self, *args, **kwargs):
            if not self._runner.is_running:
                raise RpcServerNotStartedException('the rcp server has not been started!')
            proxy = create(self.bound_address, type_id, slots, self._async, *args, **kwargs)
            self._log.debug(
                'created proxy {0} for instance id: {1} of typeid: {2}'.format(type(proxy), proxy.id, type_id))
            return proxy

        proxy_creator.__name__ = type_id
        setattr(cls, type_id, proxy_creator)


    def __init__(self, address=None, async=False, gevent_patch=False, retries=100, backend=None, **kwargs):
        self._log = get_logger(self.__class__.__name__)
        self._async = async
        self._backend = backend
        self._runner = BackgroundRunner(server_class=self._server_class, address=address, gevent_patch=gevent_patch,
                                        retries=retries)

    def __del__(self):
        self._runner.stop()

    @property
    def _server_class(self):
        if self._backend == 'tornado':
            return TornadoRpcServer
        else:
            return CherrypyRpcServer

    def start(self, wait=True, **kwargs):
        self._runner.start(wait, self._registry, **kwargs)

    def stop(self):
        self._runner.stop()

    def debug(self):
        if self._runner.is_running:
            dispatch(self.bound_address, Command.DEBUG)

    @property
    def bound_address(self):
        return self._runner.bound_address

