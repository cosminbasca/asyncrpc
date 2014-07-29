import pstats
import cProfile
import _bench
from asyncrpc import CherrypyWsgiRpcServer

__author__ = 'basca'


def profile_client(async=False, wait=1):
    stats_name = "profile_async_{0}.prof".format('T' if async else 'F')
    cProfile.runctx("_bench.bench(async={0})".format(async,), globals(), locals(), stats_name)
    s = pstats.Stats(stats_name)
    print '------------------------------------------------------------------------------------------------------------'
    s.strip_dirs().sort_stats("time").print_stats()

def _start_server():
    registry = {'MyClass': _bench.MyClass}
    cpsrv = CherrypyWsgiRpcServer(('127.0.0.1', 8080), registry)
    cpsrv.start()

def profile_server():
    stats_name = "profile_server.prof"
    cProfile.runctx("_start_server()", globals(), locals(), stats_name)

if __name__ == '__main__':
    pass
    profile_client(async=False, wait=True)
    # profile_client(async=True, wait=True)

    # profile_server()
