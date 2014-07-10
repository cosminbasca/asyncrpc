import inspect
from time import time, sleep
from pandas import DataFrame
import numpy.random as rnd
from geventmanager import set_level, get_logger
from geventmanager.manager import GeventManager, PreforkedSingletonManager
import gevent
from random import random

__author__ = 'basca'

set_level('warning')
# set_level('debug')

def main():
    data = [range(100) for i in xrange(1000)]
    df = DataFrame(data)

    t0 = time()
    v = df.values.tolist()
    print '[numpy tolist        ] took {0} seconds'.format(time() - t0)

    _itertuples = df.itertuples
    t0 = time()
    v = [r for r in _itertuples(index=False)]
    print '[list comprehension  ] took {0} seconds'.format(time() - t0)

    class TestObj(object):
        def m_a(self):
            print 'm_a'

        def m_b(self):
            print 'm_b'

        def m_c(self):
            print 'm_c'

        def m_d(self):
            print 'm_d'

        def m_e(self):
            print 'm_e'

        def m_f(self):
            print 'm_f'

        def m_g(self):
            print 'm_g'

    to = TestObj()
    methods = inspect.getmembers(to, predicate=inspect.ismethod)
    methods = {method_name: impl for method_name, impl in methods if not method_name.startswith('_')}

    to_call = ['m_{0}'.format(l) for l in 'abcdefg']

    calls = rnd.random_integers(0, len(to_call) - 1, 100000)

    t0 = time()
    for i in calls:
        func = methods[to_call[i]]
    print '[dict                ] took {0} seconds'.format(time() - t0)

    t0 = time()
    for i in calls:
        func = getattr(to, to_call[i])
    print '[getattr             ] took {0} seconds'.format(time() - t0)


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
        if self._w: sleep(random() * 0.8) # between 0 and .8 seconds
        return self._c


def bench_gevent_man(async=False, pooled=False, wait=False):
    class MyManager(GeventManager):
        pass

    MyManager.register("MyClass", MyClass)
    manager = MyManager(async=async, async_pooled=pooled)
    manager.start()

    my1 = manager.MyClass(counter=10, wait=wait)
    calls = 100000
    t0 = time()
    if async:
        resutls = [gevent.spawn(my1.current_counter) for i in xrange(calls)]
    else:
        resutls = [my1.current_counter() for i in xrange(calls)]
    t1 = time() - t0
    ncalls = long(float(calls) / float(t1))
    print 'DID: {0} calls / second, total {1} results'.format(ncalls, len(resutls))

    del manager
    print 'done'


def bench_prefork_man(async=False, pooled=False):
    my_instance = MyClass(counter=10)
    manager = PreforkedSingletonManager(my_instance, slots=['current_counter'], async=async, async_pooled=pooled)
    manager.start()

    manager.debug()

    my_instance = manager.proxy
    calls = 10000
    t0 = time()
    for i in xrange(calls):
        my_instance.current_counter()
    t1 = time() - t0
    ncalls = long(float(calls) / float(t1))
    print 'DID: {0} calls / second'.format(ncalls)

    del manager
    print 'done'


def bench_old_geventman(async=False, pooled=False):
    from geventmanager.__deprecated__.sockrpc import GeventManager as _GeventManager

    manager = _GeventManager(MyClass, handler_args=(), handler_kwargs={'counter': 10},
                             host=None, logger=get_logger(_GeventManager.__name__),
                             prefork=False, async=async, pooled=pooled, gevent_patch=False, concurrency=32)
    manager.start()

    my1 = manager.proxy

    calls = 10000
    t0 = time()
    for i in xrange(calls):
        my1.current_counter()
    t1 = time() - t0
    ncalls = long(float(calls) / float(t1))
    print 'DID: {0} calls / second'.format(ncalls)

    del manager
    print 'done'


if __name__ == '__main__':
    # bench_gevent_man(async=False, pooled=False)
    bench_gevent_man(async=True, pooled=False)

