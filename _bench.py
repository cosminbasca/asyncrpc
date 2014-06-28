import inspect
from time import time, sleep
from pandas import DataFrame
import numpy.random as rnd
from geventmanager.manager import GeventManager, PreforkedSingletonManager

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


class MyClass(object):
    def __init__(self, counter=0):
        self._c = counter

    def add(self, value=1):
        self._c += value

    def dec(self, value=1):
        self._c -= value

    def current_counter(self):
        return self._c

def main2():
    class MyManager(GeventManager):
        pass

    MyManager.register("MyClass", MyClass)
    manager = MyManager(async=False)
    # manager = MyManager(async=True, async_pooled=False)
    # manager = MyManager(async=True, async_pooled=True)
    print '[1 >]'
    manager.start()

    print '[2 >]'
    my1 = manager.MyClass(counter=10)
    my2 = manager.MyClass(counter=20)
    # my3 = manager.MyClass(counter=30)
    # my4 = manager.MyClass(counter=40)
    # my5 = manager.MyClass(counter=50)

    manager.debug()

    print '[3.1 >]'
    my1.add()
    print '[3.2 >]'
    my2.add()
    print '[3.3 >]'
    my2.add()
    # my4.add()

    manager.debug()

    print "My 1 = {0}".format(my1.current_counter())
    print "My 2 = {0}".format(my2.current_counter())
    # print "My 3 = {0}".format(my3.current_counter())
    # print "My 4 = {0}".format(my4.current_counter())
    # print "My 5 = {0}".format(my5.current_counter())

    del manager
    print 'done'


def main3():
    my_instance = MyClass(counter=10)
    print 'instance counter = {0}'.format(my_instance.current_counter())
    my_instance.add(15)
    print 'instance counter = {0}'.format(my_instance.current_counter())
    manager = PreforkedSingletonManager(my_instance, slots=['current_counter'], async=False)
    manager.start()

    manager.debug()

    my_instance = manager.proxy
    print 'instance counter = {0}'.format(my_instance.current_counter())
    try:
        my_instance.add(15)
    except ValueError, e:
        print 'called add (error) : ',e
    print 'instance counter = {0}'.format(my_instance.current_counter())

    del manager
    print 'done'


if __name__ == '__main__':
    # main()
    print '------------------------------------------------------------------------------------------------------------'
    main2()
    # sleep(1)
    print '------------------------------------------------------------------------------------------------------------'
    main3()
    # [numpy tolist        ] took 0.00174593925476 seconds      numpy tolist is 25x faster than list comprehension
    # [list comprehension  ] took 0.0259149074554 seconds
    # [dict                ] took 0.0167138576508 seconds       DICT 2x faster than getattr
    # [getattr             ] took 0.028911113739 seconds


