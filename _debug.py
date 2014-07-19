from multiprocessing.pool import ThreadPool
from time import time
from gevent.pool import Pool
import numpy as np
from asyncrpc.manager import AsyncManager
from asyncrpc.log import set_level

set_level('critical')

__author__ = 'basca'

class MyClass(object):
    def __init__(self, counter=0, workload=False):
        self._c = counter
        self._w = workload
        print 'with workload = ',True if self._w else False

    def add(self, value=1):
        self._c += value

    def dec(self, value=1):
        self._c -= value

    def current_counter(self):
        if self._w: self._c = np.exp(np.arange(1000000)).sum()
        return self._c

def bench_gevent_man(async=False, workload=False):
    class MyManager(AsyncManager):
        pass

    MyManager.register("MyClass", MyClass)
    manager = MyManager(async=async)
    manager.start()

    my1 = manager.MyClass(counter=10, workload=workload)
    calls = 10000
    concurrent = 12
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

if __name__ == '__main__':
    # cherrypy ...
    # no workload
    # bench_gevent_man(async=False, workload=False) # DID: 387 calls / second, total calls: 10000
    # bench_gevent_man(async=True, workload=False)  # DID: 2158 calls / second, total calls: 10000

    # with workload
    # bench_gevent_man(async=False, workload=True)    # DID: 195 calls / second, total calls: 10000
    bench_gevent_man(async=True, workload=True)     # DID: 169 calls / second, total calls: 10000