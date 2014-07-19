from unittest import TestCase
from asyncrpc.client import Proxy, AsyncProxy
from asyncrpc.log import set_level
from asyncrpc.manager import AsyncManager

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

    def test_01_geventmanager_blocking(self):

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

    def test_02_geventmanager_async(self):
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
