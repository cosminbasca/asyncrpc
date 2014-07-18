from abc import ABCMeta, abstractmethod
from functools import partial
import socket
import traceback
import errno
from asyncrpc.log import get_logger, set_level
from asyncrpc.exceptions import get_exception, ConnectionDownException, ConnectionTimeoutException
from werkzeug.exceptions import abort
from msgpackutil import loads, dumps
import requests
import grequests

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
        print 'deleting proxy ... '
        if self._owner:
            print 'proxy is owner '
            self._log.debug('releasing server-side instance {0}'.format(self._id))
            self.dispatch('#DEL')

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

            exception = get_exception(error, self._host)
            self._log.error('exception: {0}, {1}'.format(type(exception), exception))
            raise exception
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
                    raise
            else:
                raise

    def dispatch(self, command):
        if not command.startswith('#'):
            raise ValueError('{0} is not a valid formed command'.format(command))
        self._httpcall(command)


# ----------------------------------------------------------------------------------------------------------------------
#
# Requests / GRequests proxy implementation
#
# ----------------------------------------------------------------------------------------------------------------------
class RequestsProxy(RpcProxy):
    def __init__(self, instance_id, address, slots=None, owner=True, **kwargs):
        super(RequestsProxy, self).__init__(instance_id, address, slots=None, owner=True)
        self._post = partial(requests.post, self._url)

    def _httpcall(self, message):
        return self._post(data=message)

    def _content(self, response):
        return response.content

    def _status_code(self, response):
        return response.status_code


def dispatch(address, command, typeid=None):
    if not command.startswith('#'):
        raise ValueError('{0} is not a valid formed command'.format(command))
    post = partial(requests.post, 'http://{0}:{1}/rpc'.format(address[0], address[1]))
    response = post(data=dumps((typeid, command, [], {})))
    result, error = loads(response.content)
    if not error:
        return result
    raise get_exception(error, address[0])


if __name__ == '__main__':
    from time import time
    from multiprocessing.pool import ThreadPool

    set_level('critical')

    oid = dispatch(('127.0.0.1', 8080), '#INIT', typeid='MyClass')
    print 'have OID={0}'.format(oid)
    proxy = RequestsProxy(oid, ('127.0.0.1', 8080), async=False)
    print proxy.current_counter()
    proxy.add(value=30)
    print proxy.current_counter()
    # del proxy

    calls = 10000
    concurrent = 512
    t0 = time()
    pool = ThreadPool(concurrent)
    [pool.apply_async(proxy.current_counter) for i in xrange(calls)]
    pool.close()
    pool.join()
    t1 = time() - t0
    ncalls = long(float(calls) / float(t1))
    print 'DID: {0} calls / second, total calls: {1}'.format(ncalls, calls)

    dispatch(('127.0.0.1', 8080), '#DEBUG')
    dispatch(('127.0.0.1', 8080), '#CLEAR')
    dispatch(('127.0.0.1', 8080), '#DEBUG')
