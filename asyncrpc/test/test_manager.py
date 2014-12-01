import traceback
from unittest import TestCase
from asyncrpc.client import Proxy, AsyncProxy, AsyncSingleInstanceProxy
from asyncrpc.log import set_logger_level, LOGGER_NAME, DEBUG, setup_logger, uninstall_logger
from asyncrpc.manager import AsyncManager
from asyncrpc.tornadorpc import TornadoManager, TornadoHttpRpcProxy, TornadoAsyncHttpRpcProxy, asynchronous, async_call
from tornado import gen
from cPickle import dumps, loads

__author__ = 'basca'

setup_logger(name=LOGGER_NAME)
set_logger_level(DEBUG, name=LOGGER_NAME)
uninstall_logger()

class MyClass(object):
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
        self._innerval = 10

    @asynchronous
    def sum(self, addr, val):
        vals = yield async_call(addr).add(val)
        sv = sum(vals)
        raise gen.Return(sv)


SUCCESS = 100101102103


def capture_exception(func):
    def wrapper(*args, **kwargs):
        try:
            rv = func(*args, **kwargs)
            if rv == SUCCESS:
                print 'Function {0} completed successfully'.format(func.__name__)
            else:
                print 'Function {0} completed with failure!'.format(func.__name__)
            return rv
        except Exception, e:
            print 'Got exception {0}, while running {1}'.format(e, func.__name__)
            print traceback.format_exc()

    wrapper.__name__ = func.__name__
    return wrapper


class TestManager(TestCase):
    def setUp(self):
        # set_logger_level('critical')
        # set_level('debug')
        pass

    def _threaded_manager(self, async=False):
        class MyManager(AsyncManager):
            pass

        MyManager.register("MyClass", MyClass)
        return MyManager(async=async)

    @capture_exception
    def test_01_tornadomanager_blocking(self):
        instance = MyClass(counter=10)
        manager = TornadoManager(instance, async=False)
        manager.start()

        self.assertIsInstance(manager, TornadoManager)

        my_instance = manager.proxy()
        self.assertIsInstance(my_instance, TornadoHttpRpcProxy)

        self.assertEqual(my_instance.current_counter(), 10)
        my_instance.add(20)
        self.assertEqual(my_instance.current_counter(), 30)
        my_instance.dec(30)
        self.assertEqual(my_instance.current_counter(), 0)

        del manager
        return SUCCESS

    @capture_exception
    def test_02_tornadomanager_blocking_multiple(self):
        instance = MyClass(counter=10)
        manager = TornadoManager(instance, async=False)
        manager.start()

        manager2 = TornadoManager(instance, async=False)
        manager2.start()

        self.assertIsInstance(manager, TornadoManager)

        my_instance = manager.proxy()
        self.assertIsInstance(my_instance, TornadoHttpRpcProxy)

        self.assertEqual(my_instance.current_counter(), 10)
        my_instance.add(20)
        self.assertEqual(my_instance.current_counter(), 30)
        my_instance.dec(30)
        self.assertEqual(my_instance.current_counter(), 0)

        manager.stop()

        my_instance = manager2.proxy()
        self.assertIsInstance(my_instance, TornadoHttpRpcProxy)

        self.assertEqual(my_instance.current_counter(), 10)
        my_instance.add(20)
        self.assertEqual(my_instance.current_counter(), 30)
        my_instance.dec(30)
        self.assertEqual(my_instance.current_counter(), 0)

        manager2.stop()
        return SUCCESS

    @capture_exception
    def test_03_tornadomanager_async(self):
        instance = MyClass(counter=10)
        manager = TornadoManager(instance, async=True)
        manager.start()
        self.assertIsInstance(manager, TornadoManager)

        my_instance = AsyncSingleInstanceProxy(manager.bound_address)

        cc = my_instance.current_counter()
        self.assertEqual(cc, 10)
        my_instance.add(20)
        cc = my_instance.current_counter()
        self.assertEqual(cc, 30)
        my_instance.dec(30)
        cc = my_instance.current_counter()
        self.assertEqual(cc, 0)

        del manager
        return SUCCESS

    @capture_exception
    def test_04_tornadomanager_async_multi(self):
        instance = AsyncClass()
        manager = TornadoManager(instance, async=True)
        manager.start()

        i1 = MyClass(counter=1)
        m1 = TornadoManager(i1, async=True)
        m1.start()

        i2 = MyClass(counter=2)
        m2 = TornadoManager(i2, async=True)
        m2.start()

        cc = AsyncSingleInstanceProxy(manager.bound_address).sum([m1.bound_address, m2.bound_address], 1)
        self.assertEqual(cc, 5)

        del m1
        del m2
        del manager
        return SUCCESS

    @capture_exception
    def test_05_geventmanager_blocking(self):
        manager = self._threaded_manager(async=False)
        manager.start()

        self.assertIsInstance(manager, AsyncManager)

        my_instance = manager.MyClass(counter=10)
        self.assertIsInstance(my_instance, Proxy)

        self.assertEqual(my_instance.current_counter(), 10)
        my_instance.add(20)
        self.assertEqual(my_instance.current_counter(), 30)
        my_instance.dec(30)
        self.assertEqual(my_instance.current_counter(), 0)

        del manager
        return SUCCESS

    @capture_exception
    def test_06_geventmanager_async(self):
        manager = self._threaded_manager(async=True)
        manager.start()

        self.assertIsInstance(manager, AsyncManager)

        my_instance = manager.MyClass(counter=10)
        self.assertIsInstance(my_instance, AsyncProxy)

        self.assertEqual(my_instance.current_counter(), 10)
        my_instance.add(20)
        self.assertEqual(my_instance.current_counter(), 30)
        my_instance.dec(30)
        self.assertEqual(my_instance.current_counter(), 0)

        del manager
        return SUCCESS

    @capture_exception
    def test_07_tornadomanager_blocking_pickle(self):
        instance = MyClass(counter=10)
        manager = TornadoManager(instance, async=False)
        manager.start()

        self.assertIsInstance(manager, TornadoManager)

        my_instance = manager.proxy()
        _rep = dumps(my_instance)
        my_instance = loads(_rep)

        self.assertIsInstance(my_instance, TornadoHttpRpcProxy)

        self.assertEqual(my_instance.current_counter(), 10)
        my_instance.add(20)
        self.assertEqual(my_instance.current_counter(), 30)
        my_instance.dec(30)
        self.assertEqual(my_instance.current_counter(), 0)

        del manager
        return SUCCESS

    @capture_exception
    def test_08_tornadomanager_async_pickle(self):
        instance = MyClass(counter=10)
        manager = TornadoManager(instance, async=True)
        manager.start()
        self.assertIsInstance(manager, TornadoManager)

        my_instance = AsyncSingleInstanceProxy(manager.bound_address)
        _rep = dumps(my_instance)
        my_instance = loads(_rep)

        cc = my_instance.current_counter()
        self.assertEqual(cc, 10)
        my_instance.add(20)
        cc = my_instance.current_counter()
        self.assertEqual(cc, 30)
        my_instance.dec(30)
        cc = my_instance.current_counter()
        self.assertEqual(cc, 0)

        del manager
        return SUCCESS

    @capture_exception
    def test_09_geventmanager_blocking_pickle(self):
        manager = self._threaded_manager(async=False)
        manager.start()

        self.assertIsInstance(manager, AsyncManager)

        my_instance = manager.MyClass(counter=10)
        my_instance.owner = False
        _rep = dumps(my_instance)
        my_instance = loads(_rep)
        self.assertIsInstance(my_instance, Proxy)

        self.assertEqual(my_instance.current_counter(), 10)
        my_instance.add(20)
        self.assertEqual(my_instance.current_counter(), 30)
        my_instance.dec(30)
        self.assertEqual(my_instance.current_counter(), 0)

        del manager
        return SUCCESS

    @capture_exception
    def test_10_geventmanager_async_pickle(self):
        manager = self._threaded_manager(async=True)
        manager.start()

        self.assertIsInstance(manager, AsyncManager)

        my_instance = manager.MyClass(counter=10)
        my_instance.owner = False
        _rep = dumps(my_instance)
        my_instance = loads(_rep)
        self.assertIsInstance(my_instance, AsyncProxy)

        self.assertEqual(my_instance.current_counter(), 10)
        my_instance.add(20)
        self.assertEqual(my_instance.current_counter(), 30)
        my_instance.dec(30)
        self.assertEqual(my_instance.current_counter(), 0)

        del manager
        return SUCCESS