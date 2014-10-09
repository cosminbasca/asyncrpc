from unittest import TestCase
from asyncrpc.client import Proxy, AsyncProxy
from asyncrpc.log import set_level, get_logger
from asyncrpc.manager import AsyncManager
from asyncrpc.tornadorpc import TornadoManager, TornadoHttpRpcProxy, TornadoAsyncHttpRpcProxy, asynchronous, async_call
from tornado import gen

__author__ = 'basca'

class MyClass(object):
    def __init__(self, counter=0):
        self._c = counter

    def add(self, value=1):
        self._c += value

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
        raise gen.Return(sum(vals))


class TestManager(TestCase):
    def setUp(self):
        # set_level('critical')
        set_level('debug')

    def _threaded_manager(self, async=False):
        class MyManager(AsyncManager):
            pass

        MyManager.register("MyClass", MyClass)
        return MyManager(async=async)

    # def test_01_tornadomanager_blocking(self):
    #
    #     instance = MyClass(counter=10)
    #     manager = TornadoManager(instance, async=False)
    #     manager.start()
    #
    #     self.assertIsInstance(manager, TornadoManager)
    #
    #     my_instance = manager.proxy()
    #     self.assertIsInstance(my_instance, TornadoHttpRpcProxy)
    #
    #     self.assertEqual(my_instance.current_counter(), 10)
    #     my_instance.add(20)
    #     self.assertEqual(my_instance.current_counter(), 30)
    #     my_instance.dec(30)
    #     self.assertEqual(my_instance.current_counter(), 0)
    #
    #     del manager
    #     print 'done 01'
    #
    # def test_02_tornadomanager_blocking_multiple(self):
    #
    #     instance = MyClass(counter=10)
    #     manager = TornadoManager(instance, async=False)
    #     manager.start()
    #
    #     manager2 = TornadoManager(instance, async=False)
    #     manager2.start()
    #
    #     self.assertIsInstance(manager, TornadoManager)
    #
    #     my_instance = manager.proxy()
    #     self.assertIsInstance(my_instance, TornadoHttpRpcProxy)
    #
    #     self.assertEqual(my_instance.current_counter(), 10)
    #     my_instance.add(20)
    #     self.assertEqual(my_instance.current_counter(), 30)
    #     my_instance.dec(30)
    #     self.assertEqual(my_instance.current_counter(), 0)
    #
    #     manager.stop()
    #
    #     my_instance = manager2.proxy()
    #     self.assertIsInstance(my_instance, TornadoHttpRpcProxy)
    #
    #     self.assertEqual(my_instance.current_counter(), 10)
    #     my_instance.add(20)
    #     self.assertEqual(my_instance.current_counter(), 30)
    #     my_instance.dec(30)
    #     self.assertEqual(my_instance.current_counter(), 0)
    #
    #     manager2.stop()
    #     print 'done 02'
    #
    # @asynchronous
    # def test_03_tornadomanager_async(self):
    #     instance = MyClass(counter=10)
    #     manager = TornadoManager(instance, async=True)
    #     manager.start()
    #
    #     self.assertIsInstance(manager, TornadoManager)
    #
    #     my_instance = manager.proxy()
    #     self.assertIsInstance(my_instance, TornadoAsyncHttpRpcProxy)
    #
    #     cc = yield my_instance.current_counter()
    #     self.assertEqual(cc, 10)
    #     my_instance.add(20)
    #     cc = yield my_instance.current_counter()
    #     self.assertEqual(cc, 30)
    #     my_instance.dec(30)
    #     cc = yield my_instance.current_counter()
    #     self.assertEqual(cc, 0)
    #
    #     del manager
    #     print 'done 03'
    #
    # def test_04_geventmanager_blocking(self):
    #
    #     manager = self._threaded_manager(async=False)
    #     manager.start()
    #
    #     self.assertIsInstance(manager, AsyncManager)
    #
    #     my_instance = manager.MyClass(counter=10)
    #     self.assertIsInstance(my_instance, Proxy)
    #
    #     self.assertEqual(my_instance.current_counter(), 10)
    #     my_instance.add(20)
    #     self.assertEqual(my_instance.current_counter(), 30)
    #     my_instance.dec(30)
    #     self.assertEqual(my_instance.current_counter(), 0)
    #
    #     del manager
    #     print 'done 04'
    #
    # def test_05_geventmanager_async(self):
    #     manager = self._threaded_manager(async=True)
    #     manager.start()
    #
    #     self.assertIsInstance(manager, AsyncManager)
    #
    #     my_instance = manager.MyClass(counter=10)
    #     self.assertIsInstance(my_instance, AsyncProxy)
    #
    #     self.assertEqual(my_instance.current_counter(), 10)
    #     my_instance.add(20)
    #     self.assertEqual(my_instance.current_counter(), 30)
    #     my_instance.dec(30)
    #     self.assertEqual(my_instance.current_counter(), 0)
    #
    #     del manager
    #     print 'done 05'

    @asynchronous
    def test_06_tornadomanager_async_multi(self):
        try:
            print '1'
            instance = AsyncClass()
            print '2'
            manager = TornadoManager(instance, async=True)
            print '3'
            manager.start()

            print '4'

            i1 = MyClass(counter=1)
            print '5'
            i2 = MyClass(counter=2)
            print '6'
            m1 = TornadoManager(i1, async=True)
            print '7'
            m2 = TornadoManager(i2, async=True)
            print '8'
            m1.start()
            print '9'
            m2.start()
            print '10'

            my_instance = manager.proxy()
            print '11'
            self.assertIsInstance(my_instance, TornadoAsyncHttpRpcProxy)
            print '12'
            print m1.bound_address
            print m2.bound_address
            print my_instance
            cc = yield my_instance.sum([ m1.bound_address, m2.bound_address ], 1)
            print '13'
            self.assertEqual(cc, 5)
            print '14'

            del m1
            del m2
            del manager
            print 'done 06'
        except Exception as ex:
            print 'EXCEption ex=',ex