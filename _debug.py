from functools import partial
from multiprocessing.managers import BaseManager
from multiprocessing.pool import ThreadPool
import random
from time import time, sleep
import traceback
from gevent.pool import Pool
import numpy as np
from tornado import gen
from asyncrpc import CherrypyWsgiRpcServer, TornadoManager, TornadoAsyncHttpRpcProxy, get_logger, \
    AsyncSingleInstanceProxy
from asyncrpc.client import hidden
from asyncrpc.manager import AsyncManager
from asyncrpc.log import set_logger_level
from asyncrpc.tornadorpc import async_call, call, TornadoRpcServer, asynchronous

# set_level('info', name='asyncrpc')
set_logger_level('critical', name='asyncrpc')

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

class MyClass2(object):
    def __init__(self, counter=0):
        self._c = counter

    def add(self, value=1):
        self._c += value
        return self._c

    def dec(self, value=1):
        self._c -= value

    def current_counter(self):
        return self._c

class AsyncClass(object):
    def __init__(self):
        self._log = get_logger(owner=self)
        self._log.debug('################ CREATED ASYNCCLASS INSTANCE')

    @asynchronous
    def sum(self, addr, val):
        self._log.debug('################ CALLING SUM')
        vals = yield async_call(addr).add(val)
        self._log.debug('################ VALS = %s',vals)
        sv = sum(vals)
        raise gen.Return(sv)

    def some(self, x, y):
        return x + y


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
        def __init__(self):
            self._unattr = 10
            self.ttr_er = 20

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

        @asynchronous
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

        def another(self):
            pass

    aclass = AClass()
    server = TornadoRpcServer(('127.0.0.1', 8080), aclass, debug=True)

    # registry = {'AClass': AClass}
    # server = CherrypyWsgiRpcServer(('127.0.0.1', 8080), registry)
    # server._registry.set(hash(aclass), aclass)
    # server._registry.set("12213231231", AClass())
    # server._registry.set("12432432432", AClass())

    server.server_forever()


@asynchronous
def do_multicast():
    print 'multicast .. '
    try:
        instance = AsyncClass()
        manager = TornadoManager(instance, async=True)
        manager.start()

        i1 = MyClass2(counter=1)
        i2 = MyClass2(counter=2)
        m1 = TornadoManager(i1, async=True)
        m2 = TornadoManager(i2, async=True)
        m1.start()
        m2.start()

        cc = call(manager.bound_address).some(10, 11)
        print 'CC1 = ',cc

        cc = AsyncSingleInstanceProxy(manager.bound_address).sum([ m1.bound_address, m2.bound_address ], 1)
        print 'CC2 = ', cc

        del m1
        del m2
        del manager
    except Exception as ex:
        print 'EXCEption ex: ',ex
        print traceback.format_exc()

if __name__ == '__main__':
    # pass
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
    # do_multicast()