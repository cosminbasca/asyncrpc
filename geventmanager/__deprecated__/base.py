__author__ = 'basca'

# ================================================================================================
#
# Avalanche Exceptions
#
# ================================================================================================
class AvaBaseException(Exception):                  pass


class HostsNotReachableException(AvaBaseException): pass


class ConnectionTimeoutException(AvaBaseException): pass


class EmptyResultSetException(AvaBaseException):    pass


class SubqueryNotFound(AvaBaseException):           pass


class InvalidQuery(AvaBaseException):               pass


class PlanIsFederatedException(AvaBaseException):   pass


class ProgrammingError(AvaBaseException):           pass


class TimeoutEventException(AvaBaseException):      pass


class QueryHaltException(AvaBaseException):         pass


class EndpointFailException(AvaBaseException):      pass


class ZeroCardinalityException(AvaBaseException):   pass


class GDataException(AvaBaseException):             pass


# ================================================================================================
#
# Remote Exception handling utils
#
# ================================================================================================
class AvaServerException(AvaBaseException):
    def __init__(self, args, host=None):
        super(AvaServerException, self).__init__(args)
        self.host = host

    def __str__(self):
        return 'Server exception reason: "%s" on "%s"' % (self.args, self.host)


class MalformedResponseException(AvaServerException):
    def __str__(self):
        return 'Malformed response: "%s" received from "%s"' % (self.args, self.host)


class ConnectionClosedException(AvaServerException):
    def __str__(self):
        return 'Connection closed reason: "%s" on "%s"' % (self.args, self.host)


class AvaRemoteException(AvaServerException):
    def __init__(self, name, args, traceback, host=None):
        super(AvaRemoteException, self).__init__(args, host=host)
        self.name = name
        self.traceback = traceback


class ConnectionDownException(AvaRemoteException):  pass


