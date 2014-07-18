from abc import ABCMeta, abstractmethod
from functools import partial
import socket
import traceback
import errno
from asyncrpc.log import get_logger, set_level
from asyncrpc.exceptions import get_exception, ConnectionDownException, ConnectionTimeoutException
from asyncrpc.wsgi import Command
from werkzeug.exceptions import abort
from msgpackutil import loads, dumps
import requests

__author__ = 'basca'
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
        self._url = 'http://{0}:{1}/rpc'.format(host, port)

    def __del__(self):
        self.release()

    def release(self):
        if self._owner:
            self._log.debug('releasing server-side instance {0}'.format(self._id))
            self.dispatch(Command.RELASE)

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
                                              host=self._host)
            result, error = loads(content)
            if not error:
                return result

            raise get_exception(error, self._host)
        else:
            abort(status_code)

    def _rpccall(self, name, *args, **kwargs):
        try:
            message = dumps((self._id, name, args, kwargs))
            response = self._httpcall(message)
            return self._get_result(response)
        except socket.timeout:
            raise ConnectionTimeoutException(self._address)
        except socket.error, err:
            if isinstance(err.args, tuple):
                if err[0] == errno.ETIMEDOUT:
                    raise ConnectionTimeoutException(self._address)
                elif err[0] in [errno.ECONNRESET, errno.ECONNREFUSED]:
                    raise ConnectionDownException(repr(socket.error), err, traceback.format_exc(), host=self._host)
                else:
                    raise err
            else:
                raise err

    def dispatch(self, command, *args, **kwargs):
        if not command.startswith('#'):
            raise ValueError('{0} is not a valid formed command'.format(command))
        self._rpccall(command, *args, **kwargs)


# ----------------------------------------------------------------------------------------------------------------------
#
# Requests proxy implementation
#
# ----------------------------------------------------------------------------------------------------------------------
class RequestsProxy(RpcProxy):
    def __init__(self, instance_id, address, slots=None, owner=True, **kwargs):
        super(RequestsProxy, self).__init__(instance_id, address, slots=slots, owner=owner)
        self._post = partial(requests.post, self._url)

    def _httpcall(self, message):
        return self._post(data=message)

    def _content(self, response):
        return response.content

    def _status_code(self, response):
        return response.status_code


class ProxyFactory(object):
    def __init__(self):
        self._cache = dict()

    @staticmethod
    def instance():
        if not hasattr(ProxyFactory, "_instance"):
            ProxyFactory._instance = ProxyFactory()
        return ProxyFactory._instance

    def _cached_proxy(self, address, typeid):
        _proxy = self._cache.get((address, typeid), None)
        if not _proxy:
            _proxy = RequestsProxy(typeid, address)
            self._cache[(address, typeid)] = _proxy
        return _proxy

    def create(self, address, typeid, slots=None, *args, **kwargs):
        creator = self._cached_proxy(address, typeid)
        return RequestsProxy(creator.dispatch(Command.NEW, *args, **kwargs), address, slots=slots)

    def dispatch(self, address, command):
        if not command.startswith('#'):
            raise ValueError('{0} is not a valid command'.format(command))
        return self._cached_proxy(address, None).dispatch(command)

    def clear(self):
        for k, creator in self._cache:
            creator.release()
        self._cache.clear()


def create(address, typeid, slots=None, *args, **kwargs):
    return ProxyFactory.instance().create(address, typeid, slots, *args, **kwargs)


def dispatch(address, command):
    return ProxyFactory.instance().dispatch(address, command)


if __name__ == '__main__':
    proxy = create(('127.0.0.1', 8080), 'MyClass', counter=100)
    print proxy.current_counter()
    proxy.add(value=30)
    print proxy.current_counter()
    proxy.release()
    del proxy

    dispatch(('127.0.0.1', 8080), Command.DEBUG)
    dispatch(('127.0.0.1', 8080), Command.CLEAR)
    dispatch(('127.0.0.1', 8080), Command.DEBUG)
