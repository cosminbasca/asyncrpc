from multiprocessing.managers import BaseManager
from time import time, sleep
from asyncrpc import set_level, create
from asyncrpc.manager import AsyncManager
from gevent.pool import Pool
from multiprocessing.pool import ThreadPool, Pool as MpPool
import numpy as np
from pandas import DataFrame
import random

__author__ = 'basca'

set_level('warning')


class DataClass(object):
    def __init__(self, rows=100000, columns=10):
        self._columns = list(xrange(columns))
        self._index = list(xrange(rows))
        self._dframe = DataFrame(data=[[random.randint(0, 100000) for j in xrange(columns)] for i in xrange(rows)],
                                 index=self._index,
                                 columns=self._columns)

    def get_table(self):
        return self._dframe


def bench(async=False):
    class MyManager(AsyncManager):
        pass

    MyManager.register("DataClass", DataClass)
    manager = MyManager(async=async)
    manager.start()

    my1 = manager.DataClass()
    calls = 100
    concurrent = 128
    t0 = time()
    if async:
        pool = Pool(concurrent)
        [pool.apply_async(my1.get_table) for i in xrange(calls)]
        pool.join()
    else:
        pool = ThreadPool(concurrent)
        # pool = MpPool()
        res = [pool.apply_async(my1.get_table) for i in xrange(calls)]
        pool.close()
        pool.join()
        print [r.get().sum().sum() for r in res]
    t1 = time() - t0
    ncalls = long(float(calls) / float(t1))
    print 'DID: {0} calls / second, total calls: {1}'.format(ncalls, calls)

    del manager
    print 'done'


def bench_mpman():
    class MyManager(BaseManager):
        pass

    MyManager.register("DataClass", DataClass)
    manager = MyManager()
    manager.start()

    my1 = manager.DataClass()
    calls = 1000
    concurrent = 128
    t0 = time()
    pool = ThreadPool(concurrent)
    res = [pool.apply_async(my1.get_table) for i in xrange(calls)]
    pool.close()
    pool.join()

    print [r.get().sum().sum() for r in res]

    t1 = time() - t0
    ncalls = long(float(calls) / float(t1))
    print 'DID: {0} calls / second, total calls: {1}'.format(ncalls, calls)

    del manager
    print 'done'


def client(async=False):
    my1 = create(('127.0.0.1', 8080), 'DataClass', async)
    calls = 100
    concurrent = 128
    t0 = time()
    if async:
        pool = Pool(concurrent)
        [pool.apply_async(my1.get_table) for i in xrange(calls)]
        pool.join()
    else:
        pool = ThreadPool(concurrent)
        res = [pool.apply_async(my1.get_table) for i in xrange(calls)]
        pool.close()
        pool.join()
        print [r.get().sum().sum() for r in res]
    t1 = time() - t0
    ncalls = long(float(calls) / float(t1))
    print 'DID: {0} calls / second, total calls: {1}'.format(ncalls, calls)


if __name__ == '__main__':
    pass
    bench(async=False)
    # bench(async=True)
    # sleep(5)
    # bench_mpman()
    # client(async=False)