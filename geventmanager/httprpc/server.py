from geventmanager.log import get_logger
from abc import ABCMeta
import inspect

__author__ = 'basca'

# predicates exposed by the methods, akin to cherrypy :)

class WSGIRpcApplication(object):
    pass

class WSGIRpcServer(object):
    __metaclass__ = ABCMeta

    def __init__(self, handler):
        self._handler = handler
        self._log = get_logger(self.__class__.__name__)

        methods = inspect.getmembers(self._handler, predicate=inspect.ismethod)
        methods = [(method_name, impl) for method_name, impl in methods if not method_name.startswith('_')]

        def _handler(method_name, impl):
            TornadoHandlerClass = AsyncAvaTornadoRequestHandler if getattr(impl, 'async', False)  \
                else AvaTornadoRequestHandler
            ClassName = ('%s_AsyncTornadoHandler' if hasattr(impl,
                                                             'async_rpc') else '%s_TornadoHandler') % method_name.upper()
            return type(
                ClassName, (TornadoHandlerClass,), {'do': getattr(self.rpc_handler, method_name), }
            )

        handlers = [(r'/%s' % method_name, _handler(method_name, impl)) for method_name, impl in methods]

