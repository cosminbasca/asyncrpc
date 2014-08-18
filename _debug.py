from functools import partial
from multiprocessing.managers import BaseManager
from multiprocessing.pool import ThreadPool
import random
from time import time, sleep
from gevent.pool import Pool
import numpy as np
from asyncrpc.client import hidden
from asyncrpc.manager import AsyncManager
from asyncrpc.log import set_level
from asyncrpc.tornadorpc import async_call, call, TornadoRpcServer

set_level('info', name='asyncrpc')

__author__ = 'basca'


class MyClass(object):
    def __init__(self, counter=0, workload=False):
        self._c = counter
        self._w = workload
        print 'with workload = ', True if self._w else False

    def add(self, value=1):
        self._c += value

    def dec(self, value=1):
        self._c -= value

    def current_counter(self):
        if self._w: self._c = np.exp(np.arange(1000000)).sum()
        return self._c

    def wait_op(self):
        sleep(random.randint(1, 3))
        return self._c

    def _private(self):
        pass

    @hidden
    def some_method(self):
        pass

    def another(self):
        pass


def bench_gevent_man(async=False, workload=False, backend=None, multiprocess=False, mprocman=False):
    if not async and mprocman:
        class MyManager(BaseManager):
            pass
        MyManager.register('MyClass', MyClass)
        manager = MyManager()
        manager.start()
    else:
        class MyManager(AsyncManager):
            pass
        MyManager.register("MyClass", MyClass)
        manager = MyManager(async=async, backend=backend)
        if backend=='tornado':
            manager.start(multiprocess=multiprocess)
        else:
            manager.start()

    my1 = manager.MyClass(counter=10, workload=workload)

    # calls = 10000
    calls = 10
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

    manager.stop()
    print 'done'


def async_vs_blocking():
    class MyManager(AsyncManager):
        pass

    MyManager.register("MyClass", MyClass)

    manager = MyManager(async=False)
    manager.start()

    calls = 30

    t0 = time()
    proxy = manager.MyClass(counter=10)
    # proxy.some_method()
    pool = Pool()
    [pool.apply_async(proxy.wait_op) for i in xrange(calls)]
    pool.join()
    print 'BLOCKING TOOK {0} seconds'.format(time() - t0)

    del manager

    manager = MyManager(async=True)
    manager.start()

    t0 = time()
    proxy = manager.MyClass(counter=10)
    pool = Pool()
    [pool.apply_async(proxy.wait_op) for i in xrange(calls)]
    pool.join()
    print 'ASYNC    TOOK {0} seconds'.format(time() - t0)

    del manager


def test_tornadorpc(async=False):
    calls = 10000
    concurrent = 12
    t0 = time()
    if async:
        pool = ThreadPool(concurrent)
        [pool.apply_async(call(('127.0.0.1', 8080)).do_async, args=(('127.0.0.1', 8080), 50, 45,)) for i in xrange(calls)]
        pool.close()
        pool.join()
    else:
        pool = ThreadPool(concurrent)
        [pool.apply_async(call(('127.0.0.1', 8080)).do_sync, args=(('127.0.0.1', 8080), 50, 45,)) for i in xrange(calls)]
        pool.close()
        pool.join()
    t1 = time() - t0
    ncalls = long(float(calls) / float(t1))
    print 'DID: {0} calls / second, total calls: {1}'.format(ncalls, calls)


def tornadorpc_server():
    class AClass(object):
        def simple_method(self):
            """
            this method has no arguments
            :return: None
            """
            return None

        def varargs_method(self, x, y, *args):
            """
            this method does smth
            :param x: x value
            :param y: y value
            :param args: other args
            :return: None
            """
            return None

        def kwargs_method(self, a, b, val=None, val2=10, **kwargs):
            """
            more complex
            :param a: val a
            :param b: val b
            :param val: val val
            :param val2: val val2
            :param kwargs: other
            :return: None
            """
            return None

    aclass = AClass()
    server = TornadoRpcServer(('127.0.0.1', 8080), aclass, theme=None)
    server.server_forever()

if __name__ == '__main__':
    pass
    # cherrypy ...
    # no workload
    # bench_gevent_man(async=False, workload=False) # DID: 414 calls / second, total calls: 10000
    # bench_gevent_man(async=True, workload=False)  # DID: 384 calls / second, total calls: 10000

    # with workload
    # bench_gevent_man(async=False, workload=True)    # DID: 180 calls / second, total calls: 10000
    # bench_gevent_man(async=True, workload=True)  # DID: 181 calls / second, total calls: 10000

    # Multiprocessing
    # bench_gevent_man(async=False, workload=True, mprocman=True)
    # DID: 213 calls / second, total calls: 10000


    # async_vs_blocking()

    # test_tornadorpc(async=False)      # DID: 153 calls / second, total calls: 10000
    # test_tornadorpc(async=True)         # DID: 207 calls / second, total calls: 10000
    tornadorpc_server()