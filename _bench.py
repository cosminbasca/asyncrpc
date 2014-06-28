import inspect
from time import time, sleep
from pandas import DataFrame
import numpy.random as rnd
from geventmanager import set_level
from geventmanager.manager import GeventManager, PreforkedSingletonManager

__author__ = 'basca'

set_level('warning')
# set_level('debug')

def main():
    data = [range(100) for i in xrange(1000) ]
    df = DataFrame(data)

    t0 = time()
    v = df.values.tolist()
    print '[numpy tolist        ] took {0} seconds'.format(time()-t0)

    _itertuples = df.itertuples
    t0 = time()
    v = [r for r in _itertuples(index=False)]
    print '[list comprehension  ] took {0} seconds'.format(time()-t0)

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

    calls = rnd.random_integers(0, len(to_call)-1, 100000)

    t0 = time()
    for i in calls:
        func = methods[to_call[i]]
    print '[dict                ] took {0} seconds'.format(time()-t0)

    t0 = time()
    for i in calls:
        func = getattr(to, to_call[i])
    print '[getattr             ] took {0} seconds'.format(time()-t0)


class MyClass(object):
    def __init__(self, counter=0):
        self._c = counter

    def add(self, value=1):
        self._c += value

    def dec(self, value=1):
        self._c -= value

    def current_counter(self):
        return self._c

def bench_gevent_man(async=False, pooled=False):
    class MyManager(GeventManager):
        pass

    MyManager.register("MyClass", MyClass)
    manager = MyManager(async=async, async_pooled=pooled)
    manager.start()

    my1 = manager.MyClass(counter=10)

    calls = 10000
    t0 = time()
    for i in xrange(calls):
        my1.current_counter()
    t1 = time()-t0
    ncalls = long(float(calls) / float(t1))
    print 'DID: {0} calls / second'.format(ncalls)


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
    t1 = time()-t0
    ncalls = long(float(calls) / float(t1))
    print 'DID: {0} calls / second'.format(ncalls)

    del manager
    print 'done'


if __name__ == '__main__':
    # main()
    print '------------------------------------------------------------------------------------------------------------'
    bench_gevent_man()
    # sleep(1)
    print '------------------------------------------------------------------------------------------------------------'
    bench_prefork_man()
    # [numpy tolist        ] took 0.00174593925476 seconds      numpy tolist is 25x faster than list comprehension
    # [list comprehension  ] took 0.0259149074554 seconds
    # [dict                ] took 0.0167138576508 seconds       DICT 2x faster than getattr
    # [getattr             ] took 0.028911113739 seconds


