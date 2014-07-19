import sys

__author__ = 'basca'

# =================================================================================
#
# the host definition
#
# =================================================================================
class Host(object):
    def __init__(self, name=None, port=80, latency=0, bandwidth=sys.maxint, proxy_name=None, proxy_port=None):
        self.name = name.strip()
        self.port = int(port)
        self.latency = latency
        self.bandwidth = bandwidth
        self.proxy_name = proxy_name.strip() if proxy_name else None
        self.proxy_port = int(proxy_port) if proxy_port else None

        self._tuple = (self.name, self.port)
        self._hash = hash(self._tuple)

    def __str__(self):
        return 'Host(name=%s, port=%s)' % (self.name, self.port)

    def __repr__(self):
        return self.__str__()

    def to_socket_tuple(self, proxy=False):
        if proxy:
            return self.proxy_name, self.proxy_port
        return self._tuple

    def sparql_endpoint(self):
        return 'http://%s:%s/sparql' % self.to_socket_tuple(proxy=False)

    # noinspection PyBroadException
    def __eq__(self, other):
        try:
            return self._tuple == other._tuple
        except:
            pass
        return False

    def __hash__(self):
        return self._hash


def get_host(name, port=80):
    return Host(name=name, port=port)
