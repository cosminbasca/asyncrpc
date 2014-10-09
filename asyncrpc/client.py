from abc import ABCMeta, abstractmethod
from functools import partial
import inspect
import socket
import traceback
from geventhttpclient import HTTPClient
from asyncrpc.util import format_address, format_addresses
from asyncrpc.log import get_logger
from asyncrpc.exceptions import HTTPRpcNoBodyException, handle_exception, ErrorMessage
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
# base Transport class
#
# ----------------------------------------------------------------------------------------------------------------------
class HTTPTransport(object):
    __metaclass__ = ABCMeta

    def __init__(self, address, connection_timeout):
        self._logger = get_logger(owner=self)
        self._connection_timeout = connection_timeout
        self._url_path = '/rpc'

    @property
    def url_path(self):
        return self._url_path

    @property
    def connection_timeout(self):
        return self._connection_timeout

    @abstractmethod
    def content(self, response):
        return None

    @abstractmethod
    def status_code(self, response):
        return 500

    @abstractmethod
    def __call__(self, message):
        pass


class SingleCastHTTPTransport(HTTPTransport):
    __metaclass__ = ABCMeta

    def __init__(self, address, connection_timeout):
        super(SingleCastHTTPTransport, self).__init__(address, connection_timeout)
        self._host, self._port = format_address(address)
        self._url_base = 'http://{0}:{1}'.format(self._host, self._port)

    @property
    def address(self):
        return '{0}:{1}'.format(self._host, self._port)

    @property
    def url(self):
        return '{0}{1}'.format(self._url_base, self._url_path)

    @property
    def host(self):
        return self._host

    @property
    def port(self):
        return self._port

    @property
    def url_base(self):
        return self._url_base

    @abstractmethod
    def content(self, response):
        return None

    @abstractmethod
    def status_code(self, response):
        return 500

    @abstractmethod
    def __call__(self, message):
        pass


class MultiCastHTTPTransport(HTTPTransport):
    __metaclass__ = ABCMeta

    def __init__(self, address, connection_timeout):
        super(MultiCastHTTPTransport, self).__init__(address, connection_timeout)
        if not isinstance(address, (list, set)):
            address = [address]
        self._addresses = [format_address(addr) for addr in address]
        self._url_bases = map(lambda addr: 'http://{0}:{1}'.format(*addr), self._addresses)
        self._num_sources = len(self._addresses)

    @property
    def urls(self):
        return map(lambda base: '{0}{1}'.format(base, self._url_path), self._url_bases)

    @property
    def addressess(self):
        return map(lambda addr: '{0}:{1}'.format(*addr), self._addresses)

    @property
    def num_sources(self):
        return self._num_sources

    @abstractmethod
    def content(self, response):
        return None

    @abstractmethod
    def status_code(self, response):
        return 500

    @abstractmethod
    def __call__(self, message):
        pass


class SynchronousHTTP(SingleCastHTTPTransport):
    def __init__(self, address, connection_timeout):
        super(SynchronousHTTP, self).__init__(address, connection_timeout)
        self._post = partial(requests.post, self.url)

    @retry(retry_on_exception=_if_connection_error, stop_max_attempt_number=_MAX_RETRIES)
    def __call__(self, message):
        return self._post(data=message)

    def content(self, response):
        return response.content

    def status_code(self, response):
        return response.status_code


class AsynchronousHTTP(SingleCastHTTPTransport):
    def __init__(self, address, connection_timeout):
        super(AsynchronousHTTP, self).__init__(address, connection_timeout)
        self._post = partial(HTTPClient(self.host, port=self.port, connection_timeout=self.connection_timeout,
                                        network_timeout=self.connection_timeout).post, self.url_path)

    @retry(retry_on_exception=_if_connection_error, stop_max_attempt_number=_MAX_RETRIES)
    def __call__(self, message):
        return self._post(body=message)

    def content(self, response):
        return response.read()

    def status_code(self, response):
        return response.status_code

# ----------------------------------------------------------------------------------------------------------------------
#
# base RPC proxy specification
#
# ----------------------------------------------------------------------------------------------------------------------
DEFAULT_CONNECTION_TIMEOUT = 10


class RpcProxy(object):
    __metaclass__ = ABCMeta

    def __init__(self, address, slots=None, connection_timeout=DEFAULT_CONNECTION_TIMEOUT, **kwargs):
        address = format_addresses(address)
        self._slots = slots
        self._logger = get_logger(owner=self)
        self._transport = self.get_transport(address, connection_timeout)
        if not isinstance(self._transport, HTTPTransport):
            raise ValueError('transport must be an instance of HTTPTransport')
        self._is_multicast = isinstance(self._transport, MultiCastHTTPTransport)

    @property
    def is_multicast(self):
        return self._is_multicast

    @property
    def url(self):
        return '{0}{1}'.format(self._url_base, self._url_path)

    @abstractmethod
    def get_transport(self, address, connection_timeout):
        return None

    def __getattr__(self, func):
        def func_wrapper(*args, **kwargs):
            if self._slots and func not in self._slots:
                raise ValueError('access to function {0} is restricted'.format(func))
            return self._rpc_call(func, *args, **kwargs)

        func_wrapper.__name__ = func
        self.__dict__[func] = func_wrapper
        return func_wrapper

    def _get_result(self, response):
        status_code = self._transport.status_code(response)
        content = self._transport.content(response)
        if status_code == 200:
            if content is None:
                raise HTTPRpcNoBodyException(self._address, traceback.format_exc())

            response = loads(content)
            if isinstance(response, tuple) and len(response) == 2 and \
                    (isinstance(response[1], ErrorMessage) or response[1] is None):
                result, error = response
                if not error:
                    return result
                handle_exception(error)
            else:
                return response
        else:
            self._logger.error('HTTP exception (status code: %s)\nServer response: %s', status_code, content)
            abort(status_code)

    def _process_response(self, response):
        if self.is_multicast:
            self._logger.debug('multicast call to %s sources', self._transport.num_sources)
            result = map(self._get_result, response)
        else:
            self._logger.debug('single call')
            result = self._get_result(response)
        return result

    def _message(self, name, *args, **kwargs):
        return dumps((name, args, kwargs))

    def _rpc_call(self, name, *args, **kwargs):
        self._logger.debug("calling %s", name)
        response = self._transport(self._message(name, *args, **kwargs))
        result = self._process_response(response)
        return result


# ----------------------------------------------------------------------------------------------------------------------
#
# Single instance synchronous proxy implementation
#
# ----------------------------------------------------------------------------------------------------------------------
class SingleInstanceProxy(RpcProxy):
    def get_transport(self, address, connection_timeout):
        return SynchronousHTTP(address, connection_timeout)


# ----------------------------------------------------------------------------------------------------------------------
#
# Single instance asynchronous proxy implementation
#
# ----------------------------------------------------------------------------------------------------------------------
class AsyncSingleInstanceProxy(RpcProxy):
    def get_transport(self, address, connection_timeout):
        return AsynchronousHTTP(address, connection_timeout)


# ----------------------------------------------------------------------------------------------------------------------
#
# base RPC proxy for registry based http servers
#
# ----------------------------------------------------------------------------------------------------------------------
class RegistryRpcProxy(RpcProxy):
    __metaclass__ = ABCMeta

    def __init__(self, instance_id, address, slots=None, owner=True, **kwargs):
        super(RegistryRpcProxy, self).__init__(address, slots=slots, **kwargs)
        self._id = instance_id
        self._owner = owner

    @abstractmethod
    def get_transport(self, address, connection_timeout):
        return None

    @property
    def id(self):
        return self._id

    def __del__(self):
        self.release()

    def release(self):
        if self._owner:
            try:
                self._logger.debug('releasing server-side instance %s', self._id)
                self.dispatch(Command.RELEASE)
            except ConnectionError:
                pass
            except socket.error:
                pass

    def _message(self, name, *args, **kwargs):
        return dumps((self._id, name, args, kwargs))

    def dispatch(self, command, *args, **kwargs):
        # TODO: we should use a timeout here ... for slow creating objects for example
        if not command.startswith('#'):
            raise ValueError('{0} is not a valid formed command'.format(command))
        return self._rpc_call(command, *args, **kwargs)


# ----------------------------------------------------------------------------------------------------------------------
#
# Multi instance synchronous proxy implementation
#
# ----------------------------------------------------------------------------------------------------------------------
class Proxy(RegistryRpcProxy):
    def get_transport(self, address, connection_timeout):
        return SynchronousHTTP(address, connection_timeout)


# ----------------------------------------------------------------------------------------------------------------------
#
# Multi instance asynchronous proxy implementation
#
# ----------------------------------------------------------------------------------------------------------------------
class AsyncProxy(RegistryRpcProxy):
    def get_transport(self, address, connection_timeout):
        return AsynchronousHTTP(address, connection_timeout)


# ----------------------------------------------------------------------------------------------------------------------
#
# A proxy creation factory ...
#
# ----------------------------------------------------------------------------------------------------------------------
class ProxyFactory(object):
    def __init__(self):
        self._logger = get_logger(owner=self)
        self._cache = dict()
        self._logger.debug("proxy factory initialized")

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
        self._logger.debug("get proxy: %s", _proxy)
        return _proxy

    def create(self, address, typeid, slots=None, async=False, connection_timeout=10, *args, **kwargs):
        creator = self._proxy(address, typeid)
        self._logger.debug("create %s proxy", 'async' if async else 'blocking')
        instance_id = creator.dispatch(Command.NEW, *args, **kwargs)
        self._logger.debug("got new instance id: %s", instance_id)
        if async:
            return AsyncProxy(instance_id, address, slots=slots, connection_timeout=connection_timeout)
        return Proxy(instance_id, address, slots=slots)

    def dispatch(self, address, command):
        if not command.startswith('#'):
            raise ValueError('{0} is not a valid command'.format(command))
        return self._proxy(address, None).dispatch(command)

    def clear(self):
        for k, creator in self._cache.iteritems():
            creator.release()
        self._cache.clear()


# ----------------------------------------------------------------------------------------------------------------------
#
# wrapper methods that use the singleton proxy factory
#
# ----------------------------------------------------------------------------------------------------------------------
def create(address, typeid, slots=None, async=False, connection_timeout=10, *args, **kwargs):
    return ProxyFactory.instance().create(address, typeid, slots, async, connection_timeout, *args, **kwargs)


def dispatch(address, command):
    return ProxyFactory.instance().dispatch(address, command)

