from multiprocessing.pool import ThreadPool
from time import time
from gevent.pool import Pool
import numpy as np

__author__ = 'basca'

class MyClass(object):
    def __init__(self, counter=0, wait=False):
        self._c = counter
        self._w = wait
        print 'with wait = ',True if self._w else False

    def add(self, value=1):
        self._c += value

    def dec(self, value=1):
        self._c -= value

    def current_counter(self):
        # if self._w: sleep(random() * 0.8) # between 0 and .8 seconds
        # if self._w: self._c = sum([i ** 2 for i in xrange(int(random() * 100000))])  # a computation ...
        if self._w: self._c = np.exp(np.arange(1000000)).sum()
        return self._c



def bench_gevent_man(async=False, pooled=False, wait=False):
    class MyManager(GeventManager):
        pass

    MyManager.register("MyClass", MyClass)
    manager = MyManager(async=async, async_pooled=pooled)
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