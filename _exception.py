from asyncrpc import AsyncManager, set_level

__author__ = 'basca'


class MyException(Exception):
    pass


class MyClass(object):
    def method(self, x):
        return x

    def error_method(self, y):
        raise MyException('this is my exception y={0}'.format(y))


class MyManager(AsyncManager):
    pass


MyManager.register('MyClass', MyClass)


class MyNestedClass(object):
    def __init__(self):
        self._manager = MyManager()
        self._manager.start()
        self._my_class = self._manager.MyClass()
        # print self._manager._registry


    def method(self, x):
        return self._my_class.method(x)

    def error_method(self, y):
        return self._my_class.error_method(y)


class MyNestedManager(AsyncManager):
    pass


MyNestedManager.register('MyNestedClass', MyNestedClass)


def test_remote():
    # manager = MyManager()
    # manager.start()
    #
    # try:
    #     my_class = manager.MyClass()
    #     print my_class.method(10)
    #     print my_class.error_method(20)
    # except Exception, e:
    #     print e
    # finally:
    #     del manager
    #
    # print '---------------------------------------------------------------------------------------------'

    nested_manager = MyNestedManager()
    nested_manager.start()
    # print nested_manager._registry

    try:
        my_nested_class = nested_manager.MyNestedClass()
        print my_nested_class.method(10)
        print my_nested_class.error_method(20)
    except Exception, e:
        print e
    finally:
        del nested_manager



if __name__ == '__main__':
    set_level('critical')
    test_remote()