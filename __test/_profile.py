import pstats
import cProfile

from __test import _bench
from asyncrpc import CherrypyWsgiRpcServer


__author__ = 'basca'


def profile_client(async=False):
    stats_name = "profile_async_{0}.prof".format('T' if async else 'F')
    cProfile.runctx("_bench.bench(async={0})".format(async,), globals(), locals(), stats_name)
    s = pstats.Stats(stats_name)
    print '------------------------------------------------------------------------------------------------------------'
    s.strip_dirs().sort_stats("time").print_stats()

def _start_server():
    registry = {'DataClass': _bench.DataClass}
    cpsrv = CherrypyWsgiRpcServer(('127.0.0.1', 8080), registry)
    cpsrv.start()

def profile_server():
    stats_name = "profile_server.prof"
    cProfile.runctx("_start_server()", globals(), locals(), stats_name)

if __name__ == '__main__':
    pass
    # profile_client(async=False)
    profile_client(async=True)

    # profile_server()
