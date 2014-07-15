from geventmanager.log import get_logger
from abc import ABCMeta
import inspect

__author__ = 'basca'

class HttpRpcHandler(object):
    pass

class AsyncHttpRpcHandler(object):
    pass

def get_routes(handler):
    if handler is None:
        raise ValueError('handler cannot be None')

    methods = [(method_name, impl) for method_name, impl in inspect.getmembers(handler, predicate=inspect.ismethod)
               if not method_name.startswith('_') and getattr(impl, 'exposed', False) == True]

    def route_handler(method_name, impl):
        HandlerClass = AsyncHttpRpcHandler if getattr(impl, 'async', False) else HttpRpcHandler
        class_name = '{0}_{1}'.format(HandlerClass.__name__, method_name.upper())
        return type(class_name, (HandlerClass,), {'do': getattr(handler, method_name), })


    return [(r'/%s' % method_name, route_handler(method_name, impl)) for method_name, impl in methods]


