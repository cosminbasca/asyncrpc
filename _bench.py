from time import time
from asyncrpc import set_level, create
from asyncrpc.manager import AsyncManager
from gevent.pool import Pool
from multiprocessing.pool import ThreadPool
import numpy as np

__author__ = 'basca'

set_level('warning')


class MyClass(object):
    def __init__(self, counter=0, wait=False):
        self._c = counter
        self._w = wait
        print 'with wait = ', True if self._w else False

    def add(self, value=1):
        self._c += value

    def dec(self, value=1):
        self._c -= value

    def current_counter(self):
        if self._w: self._c = np.exp(np.arange(1000000)).sum()
        return self._c


def bench(async=False, wait=False):
    class MyManager(AsyncManager):
        pass

    MyManager.register("MyClass", MyClass)
    manager = MyManager(async=async)
    manager.start(threads=512)

    my1 = manager.MyClass(counter=10, wait=wait)
    calls = 10000
    concurrent = 512
    t0 = time()
    if async:
        pool = Pool(concurrent)
        [pool.apply_async(my1.current_counter) for i in xrange(calls)]
        pool.join()
    else:
        pool = ThreadPool(concurrent)
        [pool.apply_async(my1.current_counter) for i in xrange(calls)]
        pool.close()
        pool.join()
    t1 = time() - t0
    ncalls = long(float(calls) / float(t1))
    print 'DID: {0} calls / second, total calls: {1}'.format(ncalls, calls)

    del manager
    print 'done'


def _run_client(async=False, wait=True):
    my1 = create(('127.0.0.1', 8080), 'MyClass', None, async, counter=100, wait=wait)
    calls = 10000
    concurrent = 512
    t0 = time()
    if async:
        pool = Pool(concurrent)
        [pool.apply_async(my1.current_counter) for i in xrange(calls)]
        pool.join()
    else:
        pool = ThreadPool(concurrent)
        [pool.apply_async(my1.current_counter) for i in xrange(calls)]
        pool.close()
        pool.join()
    t1 = time() - t0
    ncalls = long(float(calls) / float(t1))
    print 'DID: {0} calls / second, total calls: {1}'.format(ncalls, calls)


if __name__ == '__main__':
    _run_client(False, True)