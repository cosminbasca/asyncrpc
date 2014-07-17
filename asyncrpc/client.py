from abc import ABCMeta, abstractmethod

__author__ = 'basca'

class RpcClient(object):
    __metaclass__ = ABCMeta

    @abstractmethod
    def _body(self, response):
        return None

    @abstractmethod
    def _code(self, response):
        return 500

    @abstractmethod
    def _httpcall(self, *args, **kwargs):
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