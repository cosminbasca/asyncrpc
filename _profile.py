import pstats
import cProfile
from time import sleep
import _bench

__author__ = 'basca'


def profile(prefork=False, async=False, pooled=False, wait=1):
    call = 'bench_prefork_man' if prefork else 'bench_gevent_man'
    stats_name = "profile_{0}_async_{1}_pooled_{2}.prof".format('pfork' if prefork else 'gevent',
                                                                'T' if async else 'F',
                                                                'T' if pooled else 'F')
    cProfile.runctx("_bench.{0}(async={1}, pooled={2}, wait={3})".format(call, async, pooled, wait), globals(), locals(),
                    stats_name)
    s = pstats.Stats(stats_name)
    print '------------------------------------------------------------------------------------------------------------'
    s.strip_dirs().sort_stats("time").print_stats()


def _profile(async=False, pooled=False, wait=1):
    stats_name = "profile_{0}_async_{1}_pooled_{2}.prof".format('old',
                                                                'T' if async else 'F',
                                                                'T' if pooled else 'F')
    cProfile.runctx("_bench.{0}(async={1}, pooled={2})".format('bench_old_geventman', async, pooled), globals(),
                    locals(), stats_name)
    s = pstats.Stats(stats_name)
    print '------------------------------------------------------------------------------------------------------------'
    s.strip_dirs().sort_stats("time").print_stats()
    sleep(wait)


if __name__ == '__main__':
    # _profile(async=False, pooled=False)

    # profile(prefork=False, async=False, pooled=False, wait=False)
    # nowait            DID: 464 calls / second, total 100000 results
    # profile(prefork=False, async=False, pooled=False, wait=True)
    # randwait(0,.8)

    # profile(prefork=False, async=True, pooled=False, wait=False)
    # nowait
    profile(prefork=False, async=True, pooled=False, wait=True)
    # randwait(0,.8)

    # profile(prefork=False, async=True, pooled=True)
    # profile(prefork=True, async=False, pooled=False)
    # profile(prefork=True, async=True, pooled=False)
    # profile(prefork=True, async=True, pooled=True)