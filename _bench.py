import inspect
from time import time
import numpy as np
from pandas import DataFrame
import numpy as np
import numpy.random as rnd
from geventmanager import GeventManager

__author__ = 'basca'

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


def main2():
    class MyClass(object):
        def __init__(self, counter=0):
            self._c = counter

        def add(self, value=1):
            self._c += value

        def dec(self, value=1):
            self._c -= value

        def current_counter(self):
            return self._c

    class MyManager(GeventManager):
        pass

    MyManager.register("MyClass", MyClass)
    manager = MyManager(async=False, preforked=False)
    print '1 >'
    manager.start()

    print '2 >'
    my1 = manager.MyClass(counter=10)
    my2 = manager.MyClass(counter=20)
    my3 = manager.MyClass(counter=30)
    my4 = manager.MyClass(counter=40)
    my5 = manager.MyClass(counter=50)

    print '3 >'
    my1.inc()
    my2.inc()
    my2.inc()
    my4.inc()

    print "My 1 = {0}".format(my1.current_counter())
    print "My 2 = {0}".format(my2.current_counter())
    print "My 3 = {0}".format(my3.current_counter())
    print "My 4 = {0}".format(my4.current_counter())
    print "My 5 = {0}".format(my5.current_counter())

    print 'done'

if __name__ == '__main__':
    # main()
    main2()
    # [numpy tolist        ] took 0.00174593925476 seconds      numpy tolist is 25x faster than list comprehension
    # [list comprehension  ] took 0.0259149074554 seconds
    # [dict                ] took 0.0167138576508 seconds       DICT 2x faster than getattr
    # [getattr             ] took 0.028911113739 seconds


