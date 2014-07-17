from unittest import TestCase
from asyncrpc.log import set_level

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

