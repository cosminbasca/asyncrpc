AsyncRPC
========

AsyncRPC is a http rpc library, providing a manager similar to the *multiprocessing.Basemanager* with [gevent](http://www.gevent.org/) support.
* AsyncManager allows one to get gevent asynchronous proxies to remote objects
* The manager server(s) offer an html view over the internal state of the server (for debug purposes)
* The manager server is WSGI based, so in the future other wsgi compatible servers can be used (for now, [cherrypi](http://www.cherrypy.org/) and [tornado](http://www.tornadoweb.org/) are supported) 

Important Notes
---------------
This software is the product of research carried out at the [University of Zurich](http://www.ifi.uzh.ch/ddis.html) and comes with no warranty whatsoever. Have fun!

TODO's
------
* The project is not documented (yet)

How to Install the Project
--------------------------
To install **AsyncRPC** you have two options: 1) manual installation (install requirements first) or 2) automatic with **pip**

Install the project manually from source (after downloading it locally):
```sh
$ python setup.py install
```

Install the project with pip:
```sh
$ pip install https://github.com/cosminbasca/asyncrpc
```

Also have a look at the test.sh scripts included in the codebase 

Examples
--------

For more information have a look at the tests inside *asyncrpc.test*

```python
from asyncrpc.manager import AsyncManager

class FooClass(object):
    def __init__(self, init_bar=-1):
        self.bar = init_bar

    def foo(self, val):
        self.bar += val
        return self.bar

class FooManager(AsyncManager):
    pass

FooManager.register("FooClass", FooClass)

manager = FooManager(async=True)
manager.start()

my_foo = manager.FooClass(100)
# should print 100
print my_foo.foo(0)
# should print 200
print my_foo.foo(100)
# should print 200
print my_foo.foo(0)
```

Thanks a lot to
---------------
* [University of Zurich](http://www.ifi.uzh.ch/ddis.html) and the [Swiss National Science Foundation](http://www.snf.ch/en/Pages/default.aspx) for generously funding the research that led to this software.
