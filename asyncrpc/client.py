from abc import ABCMeta, abstractmethod
import socket
import traceback
import errno
from asyncrpc.log import get_logger
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
        if self._owner:
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
    def __init__(self, instance_id, address, slots=None, owner=True, async=True, **kwargs):
        super(RequestsProxy, self).__init__(instance_id, address, slots=None, owner=True)
        self._async = async

        self._post = grequests.post if self._async else requests.post

    @property
    def async(self):
        return self._async

    def _httpcall(self, message):
        self._post(self._url, data=message)

    def _content(self, response):
        return response.text

    def _status_code(self, response):
        return response.status_code

