from abc import ABCMeta, abstractmethod
import traceback
from asyncrpc.log import get_logger

__author__ = 'basca'

class RpcProxy(object):
    __metaclass__ = ABCMeta

    def __init__(self, instance_id, address, slots=None, owner=True):
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

    def __del__(self):
        if self._owner:
            self._log.debug('releasing server-side instance {0}'.format(self._id))
            self.send('#DEL')

    @abstractmethod
    def _body(self, response):
        return None

    @abstractmethod
    def _code(self, response):
        return 500

    @abstractmethod
    def _httpcall(self, *args, **kwargs):
        pass

    @classmethod
    def instance(cls, host):
        """return a client instance for a particular HOST, a client factory!"""
        return cls(host)

    def __init__(self, address, func=None):
        self._address = address
        self._func = func

    def __getattr__(self, func):
        _callable = self.__class__(self._host, use_proxy=self._use_proxy, func=func)
        self.__dict__[func] = _callable
        return _callable

    @abstractmethod
    def __call__(self, *args, **kwargs):
        pass


    def _rpc(self, body):
        if body is None:
            raise ConnectionDownException('http body is None', None, traceback.format_exc(), host=self._host)

        result, error = loads(body)
        if not error:
            return result

        exception = get_exception(error, self._host)
        # logger.debug('[HTTP CLIENT] got exception = %s, %s'%(type(exception), exception))
        raise exception

    def _result(self, response):
        code = self._code(response)
        body = self._body(response)
        return self._rpc(body)

    def __call__(self, *args, **kwargs):
        try:
            response = self._httpcall(*args, **kwargs)
            return self._result(response)
        except socket.timeout:
            raise ConnectionTimeoutException('connection timeout to %s' % self._host)
        except socket.error, err:
            if isinstance(err.args, tuple):
                if err[0] == errno.ETIMEDOUT:
                    raise ConnectionTimeoutException('connection timeout to %s' % self._host)
                elif err[0] in [errno.ECONNRESET, errno.ECONNREFUSED]:
                    raise ConnectionDownException(repr(socket.error), err, traceback.format_exc(), host=self._host)
                else:
                    raise
            else:
                raise