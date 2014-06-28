import pstats, cProfile
from time import sleep
import _bench

__author__ = 'basca'


def profile(prefork=False, async=False, pooled=False, wait=2):
    call = 'bench_prefork_man' if prefork else 'bench_gevent_man'
    stats_name = "profile_{0}_async_{1}_pooled_{2}.prof".format('pfork' if prefork else 'gevent',
                                                                'T' if async else 'F',
                                                                'T' if pooled else 'F')
    cProfile.runctx("_bench.{0}(async={1}, pooled={2})".format(call, async, pooled), globals(), locals(),
                    stats_name)
    s = pstats.Stats(stats_name)
    print '------------------------------------------------------------------------------------------------------------'
    s.strip_dirs().sort_stats("time").print_stats()
    sleep(wait)

if __name__ == '__main__':
    profile(prefork=False, async=False, pooled=False)   # DID: 2454 calls / second
    profile(prefork=False, async=True, pooled=False)    # DID: 715 calls / second
    profile(prefork=False, async=True, pooled=True)     # DID: 391 calls / second
    profile(prefork=True, async=False, pooled=False)    # DID: 549 calls / second
    profile(prefork=True, async=True, pooled=False)     # DID: 534 calls / second
    profile(prefork=True, async=True, pooled=True)      # DID: 443 calls / second