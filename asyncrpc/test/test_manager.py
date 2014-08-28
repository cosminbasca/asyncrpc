from unittest import TestCase
from asyncrpc.client import Proxy, AsyncProxy
from asyncrpc.log import set_level
from asyncrpc.manager import AsyncManager
from asyncrpc.tornadorpc import TornadoManager, TornadoHttpRpcProxy, TornadoAsyncHttpRpcProxy, asynchronous
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


class TestManager(TestCase):
    def setUp(self):
        set_level('critical')

    def _threaded_manager(self, async=False):
        class MyManager(AsyncManager):
            pass

        MyManager.register("MyClass", MyClass)
        return MyManager(async=async)

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

    @asynchronous
    def test_03_tornadomanager_async(self):
        instance = MyClass(counter=10)
        manager = TornadoManager(instance, async=True)
        manager.start()

        self.assertIsInstance(manager, TornadoManager)

        my_instance = manager.proxy()
        self.assertIsInstance(my_instance, TornadoAsyncHttpRpcProxy)

        cc = yield my_instance.current_counter()
        self.assertEqual(cc, 10)
        my_instance.add(20)
        cc = yield my_instance.current_counter()
        self.assertEqual(cc, 30)
        my_instance.dec(30)
        cc = yield my_instance.current_counter()
        self.assertEqual(cc, 0)

        del manager

    def test_04_geventmanager_blocking(self):

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

    def test_05_geventmanager_async(self):
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

