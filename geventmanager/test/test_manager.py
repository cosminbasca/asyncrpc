from unittest import TestCase
from geventmanager import GeventManager, InetProxy, GeventProxy, GeventPooledProxy, PreforkedSingletonManager
from geventmanager.log import set_level

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

    def _threaded_manager(self, async=False, async_pooled=False):
        class MyManager(GeventManager):
            pass

        MyManager.register("MyClass", MyClass)
        return MyManager(async=async, async_pooled=async_pooled)

    def _preforked_manager(self):
        my_instance = MyClass(counter=10)
        return PreforkedSingletonManager(my_instance, slots=['current_counter'], async=False)


    def test_geventmanager_blocking(self):
        manager = self._threaded_manager(async=False, async_pooled=False)
        manager.start()

        self.assertIsInstance(manager, GeventManager)

        my_instance = manager.MyClass(counter=10)
        self.assertIsInstance(my_instance, InetProxy)

        self.assertEqual(my_instance.current_counter(), 10)
        my_instance.add(20)
        self.assertEqual(my_instance.current_counter(), 30)
        my_instance.dec(30)
        self.assertEqual(my_instance.current_counter(), 0)

        del manager

    def test_geventmanager_async_singlesocket(self):
        manager = self._threaded_manager(async=True, async_pooled=False)
        manager.start()

        self.assertIsInstance(manager, GeventManager)

        my_instance = manager.MyClass(counter=10)
        self.assertIsInstance(my_instance, GeventProxy)

        self.assertEqual(my_instance.current_counter(), 10)
        my_instance.add(20)
        self.assertEqual(my_instance.current_counter(), 30)
        my_instance.dec(30)
        self.assertEqual(my_instance.current_counter(), 0)

        del manager

    def test_geventmanager_async_pooled(self):
        manager = self._threaded_manager(async=True, async_pooled=True)
        manager.start()

        self.assertIsInstance(manager, GeventManager)

        my_instance = manager.MyClass(counter=10)
        self.assertIsInstance(my_instance, GeventPooledProxy)

        self.assertEqual(my_instance.current_counter(), 10)
        my_instance.add(20)
        self.assertEqual(my_instance.current_counter(), 30)
        my_instance.dec(30)
        self.assertEqual(my_instance.current_counter(), 0)

        del manager

    def test_preforkedmanager(self):
        manager = self._preforked_manager()
        manager.start()

        self.assertIsInstance(manager, PreforkedSingletonManager)

        my_instance = manager.proxy
        self.assertIsInstance(my_instance, InetProxy)

        self.assertEqual(my_instance.current_counter(), 10)
        with self.assertRaises(ValueError):
            my_instance.add(20)
        self.assertNotEqual(my_instance.current_counter(), 30)
        with self.assertRaises(ValueError):
            my_instance.dec(30)
        self.assertNotEqual(my_instance.current_counter(), 0)
        self.assertEqual(my_instance.current_counter(), 10)

        del manager

