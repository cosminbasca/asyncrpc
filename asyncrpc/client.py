from abc import ABCMeta, abstractmethod
from functools import partial
import inspect
import traceback
from asyncrpc.log import get_logger
from asyncrpc.exceptions import get_exception, ConnectionDownException, ConnectionTimeoutException
from asyncrpc.commands import Command
from werkzeug.exceptions import abort
from asyncrpc.messaging import dumps, loads
import requests
from requests.exceptions import ConnectionError
from retrying import retry

__author__ = 'basca'

# ----------------------------------------------------------------------------------------------------------------------
#
# general utility functions & constants
#
# ----------------------------------------------------------------------------------------------------------------------
def hidden(func):
    assert hasattr(func, '__call__'), 'func is not a callable'
    func.hidden = True
    return func


def asynchronous(func):
    assert hasattr(func, '__call__'), 'func is not a callable'
    func.asynchronous = True
    return func


def exposed_methods(obj, with_private=False):
    def exposed(func_name, func):
        if not hasattr(func, '__call__') or \
                func_name.startswith('__' if with_private else '_') or \
                hasattr(func, 'hidden'):
            return False
        return True

    methods = inspect.getmembers(obj, predicate=inspect.ismethod)
    return {method_name: impl for method_name, impl in methods if exposed(method_name, impl)}


def _if_connection_error(exception):
    return isinstance(exception, ConnectionError)


_MAX_RETRIES = 100

# ----------------------------------------------------------------------------------------------------------------------
#
# base RPC proxy specification
#
# ----------------------------------------------------------------------------------------------------------------------
class RpcProxy(object):
    __metaclass__ = ABCMeta

    def __init__(self, instance_id, address, slots=None, owner=True, **kwargs):
        if isinstance(address, (tuple, list)):
            host, port = address
        elif isinstance(address, (str, unicode)):
            host, port = address.split(':')
            port = int(port)
        else:
            raise ValueError(
                'address, must be either a tuple/list or string of the name:port form, got {0}'.format(address))

        self._id = instance_id
        self._address = (host, port)
        self._slots = slots
        self._owner = owner
        self._log = get_logger(self.__class__.__name__)
        self._url_base = 'http://{0}:{1}'.format(host, port)
        self._url_path = '/rpc'

    @property
    def id(self):
        return self._id

    @property
    def url(self):
        return '{0}{1}'.format(self._url_base, self._url_path)

    def __del__(self):
        self.release()

    def release(self):
        if self._owner:
            self._log.debug('releasing server-side instance {0}'.format(self._id))
            self.dispatch(Command.RELEASE)

    @abstractmethod
    def _content(self, response):
        return None

    @abstractmethod
    def _status_code(self, response):
        return 500

    @abstractmethod
    def _httpcall(self, message):
        pass

    def __getattr__(self, func):
        def func_wrapper(*args, **kwargs):
            if self._slots and func not in self._slots:
                raise ValueError('access to function {0} is restricted'.format(func))
            return self._rpccall(func, *args, **kwargs)

        func_wrapper.__name__ = func
        self.__dict__[func] = func_wrapper
        return func_wrapper

    def _get_result(self, response):
        status_code = self._status_code(response)
        if status_code == 200:
            content = self._content(response)
            if content is None:
                raise ConnectionDownException('http response does not have a body', None, traceback.format_exc(),
                                              self._address)
            result, error = loads(content)
            if not error:
                return result

            raise get_exception(error, self._host)
        else:
            abort(status_code)

    def _rpccall(self, name, *args, **kwargs):
        message = dumps((self._id, name, args, kwargs))
        response = self._httpcall(message)
        return self._get_result(response)

    def dispatch(self, command, *args, **kwargs):
        if not command.startswith('#'):
            raise ValueError('{0} is not a valid formed command'.format(command))
        return self._rpccall(command, *args, **kwargs)


# ----------------------------------------------------------------------------------------------------------------------
#
# Requests proxy implementation
#
# ----------------------------------------------------------------------------------------------------------------------
class Proxy(RpcProxy):
    def __init__(self, instance_id, address, slots=None, owner=True, **kwargs):
        super(Proxy, self).__init__(instance_id, address, slots=slots, owner=owner)
        self._post = partial(requests.post, self.url)

    @retry(retry_on_exception=_if_connection_error, stop_max_attempt_number=_MAX_RETRIES)
    def _httpcall(self, message):
        return self._post(data=message)

    def _content(self, response):
        return response.content

    def _status_code(self, response):
        return response.status_code


# ----------------------------------------------------------------------------------------------------------------------
#
# Requests proxy implementation
#
# ----------------------------------------------------------------------------------------------------------------------
class AsyncProxy(Proxy):
    def __init__(self, instance_id, address, slots=None, owner=True, **kwargs):
        super(AsyncProxy, self).__init__(instance_id, address, slots=slots, owner=owner, **kwargs)
        import grequests

        self._gpost = partial(grequests.AsyncRequest, 'POST', self.url)
        self._post = lambda data=None: self._gpost(data=data).send()


# ----------------------------------------------------------------------------------------------------------------------
#
# A proxy creation factory ...
#
# ----------------------------------------------------------------------------------------------------------------------
class ProxyFactory(object):
    def __init__(self):
        self._cache = dict()

    @staticmethod
    def instance():
        if not hasattr(ProxyFactory, "_instance"):
            ProxyFactory._instance = ProxyFactory()
        return ProxyFactory._instance

    def _proxy(self, address, typeid):
        _proxy = self._cache.get((address, typeid), None)
        if not _proxy:
            _proxy = Proxy(typeid, address)
            self._cache[(address, typeid)] = _proxy
        return _proxy

    def create(self, address, typeid, slots=None, async=False, *args, **kwargs):
        creator = self._proxy(address, typeid)
        instance_id = creator.dispatch(Command.NEW, *args, **kwargs)
        if async:
            return AsyncProxy(instance_id, address, slots=slots)
        return Proxy(instance_id, address, slots=slots)

    def dispatch(self, address, command):
        if not command.startswith('#'):
            raise ValueError('{0} is not a valid command'.format(command))
        return self._proxy(address, None).dispatch(command)

    def clear(self):
        for k, creator in self._cache:
            creator.release()
        self._cache.clear()


# ----------------------------------------------------------------------------------------------------------------------
#
# wrapper methods that use the singleton proxy factory
#
# ----------------------------------------------------------------------------------------------------------------------

def create(address, typeid, slots=None, async=False, *args, **kwargs):
    return ProxyFactory.instance().create(address, typeid, slots, async, *args, **kwargs)


def dispatch(address, command):
    return ProxyFactory.instance().dispatch(address, command)


if __name__ == '__main__':
    proxy = create(('127.0.0.1', 8080), 'MyClass', counter=100, async=True)
    # proxy = create(('127.0.0.1', 8080), 'MyClass', counter=100, async=False)
    print proxy
    print proxy.current_counter()
    proxy.add(value=30)
    print proxy.current_counter()
    # proxy.release()
    # del proxy

    # dispatch(('127.0.0.1', 8080), Command.DEBUG)
    # dispatch(('127.0.0.1', 8080), Command.CLEAR)
    # dispatch(('127.0.0.1', 8080), Command.DEBUG)
