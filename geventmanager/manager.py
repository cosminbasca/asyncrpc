from geventmanager.exceptions import InvalidStateException
from geventmanager.log import get_logger
from geventmanager.proxy import InetProxy, GeventProxy, GeventPooledProxy, Dispatcher
from geventmanager.server import PreforkedRpcServer, ThreadedRpcServer
from multiprocessing.managers import State
from multiprocessing import Pipe, Process
from multiprocessing.util import Finalize
from gevent.monkey import patch_all
from gevent import reinit
from time import sleep
import socket
import errno
import signal
import psutil

__author__ = 'basca'

# ----------------------------------------------------------------------------------------------------------------------
#
# a generic manager, that supports gevent cooperative sockets as well. The server can be threaded or preforked
#
# ----------------------------------------------------------------------------------------------------------------------
class GeventManager(object):
    _registry = {}

    @classmethod
    def register(cls, type_id, callable=None):
        if '_registry' not in cls.__dict__:
            cls._registry = cls._registry.copy()

        cls._registry[type_id] = callable

        def proxy_creator(self, *args, **kwargs):
            _init = Dispatcher(self._bound_address, type_id=type_id)
            instance_id = _init('#INIT', *args, **kwargs)
            if self._async:
                if self._async_pooled:
                    proxy = GeventPooledProxy(instance_id, self._bound_address, concurrency=self._pool_concurrency)
                else:
                    proxy = GeventProxy(instance_id, self._bound_address)
            else:
                proxy = InetProxy(instance_id, self._bound_address)
            return proxy

        proxy_creator.__name__ = type_id
        setattr(cls, type_id, proxy_creator)

    def __init__(self, address=None, async=False, async_pooled=False, gevent_patch=False, pool_concurrency=32,
                 preforked=False, retries=2000, **kwargs):
        self._log = get_logger(self.__class__.__name__)

        self._process = None
        self._address = address if address else ('127.0.0.1', 0)
        self._bound_address = None
        self._dispatch = None
        self._state = State()
        self._state.value = State.INITIAL

        self._async = async
        self._async_pooled = async_pooled
        self._gevent_patch = gevent_patch
        self._pool_concurrency = pool_concurrency
        self._retries = retries

        self._Server = PreforkedRpcServer if preforked else ThreadedRpcServer
        self._log.debug('manager using [{0}] server'.format(self._Server.__name__))


    def _run_server(self, writer, **kwargs):
        """ Create a server, report its address and run it """
        try:
            if self._gevent_patch:
                reinit()
                patch_all()
            server = None

            retries = 0
            while retries < self._retries:
                try:
                    server = self._Server(self._address, self._registry, **kwargs)
                    break
                except socket.timeout:
                    retries -= 1
                except socket.error, err:
                    if type(err.args) != tuple or err[0] not in [errno.ETIMEDOUT, errno.EAGAIN, errno.EADDRINUSE]:
                        raise
                    retries -= 1

            if server:
                writer.send(server.bound_address)
                writer.close()
                server.run()
            else:
                writer.close()
        except Exception, err:
            self._log.error(
                'Rpc server exited. {0}'.format('Exception on exit: {0}'.format(err if err.message else '')))


    def start(self, wait=True):
        """ start server in a different process (avoid blocking the main thread due to the servers event loop ) """
        if self._state.value != State.INITIAL:
            raise InvalidStateException('[rpc manager] has already been initialized')

        reader, writer = Pipe(duplex=False)

        self._process = Process(target=self._run_server, args=(writer,))

        identity = ':'.join(str(i) for i in self._process._identity)
        self._process.name = type(self).__name__ + '-' + identity
        self._process.start()

        writer.close()
        self._bound_address = reader.recv()
        reader.close()
        self._log.debug('server starting on {0}'.format(self._bound_address))
        self._dispatch = Dispatcher(self._bound_address)
        self._log.debug('server initialized dispatcher')

        self.shutdown = Finalize(self, self._finalize, args=(), exitpriority=0)

        if wait:
            while True:
                try:
                    if self._process.is_alive():
                        self._dispatch("#PING")
                        self._log.debug('server started OK')
                        self._state.value = State.STARTED
                        return True
                    else:
                        return False
                except:
                    sleep(0.01)
            return False
        return True

    def restart(self, wait=None):
        self._log.debug('restart')
        self.shutdown()
        self._state.value = State.INITIAL
        self.start(wait=True)
        self._log.debug('restarted')

    def stop(self):
        self.shutdown()

    def debug(self):
        self._dispatch('#DEBUG')

    def _signal_children(self):
        pid = self._process.pid
        proc = psutil.Process(pid)
        kids = proc.get_children(recursive=False)
        self._log.debug('signaling {0} request child processes'.format(len(kids)))
        for kid in kids:
            try:
                self._log.debug('\t signal request process [{0}]'.format(kid.pid))
                kid.send_signal(signal.SIGUSR1)
            except psutil.NoSuchProcess:
                self._log.error('\t process [{0}] no longer exists (skipping)'.format(kid.pid))

    # noinspection PyBroadException
    def _finalize(self):
        """ Shutdown the manager process; will be registered as a finalizer """
        if not self._process:
            return

        if self._process.is_alive():
            self._signal_children()

            self._log.debug('sending shutdown message to server')
            try:
                self._dispatch("#SHUTDOWN")
            except Exception:
                pass

            self._log.debug('wait for server-starter process to terminate')
            self._process.join(timeout=10.0)

            if self._process.is_alive():
                self._log.debug('manager still alive')
                if hasattr(self._process, 'terminate'):
                    self._log.debug('trying to `terminate()` manager process')
                    self._process.terminate()
                    self._process.join(timeout=10.0)
                    if self._process.is_alive():
                        self._log.debug('manager still alive after terminate!')
            else:
                self._log.debug('server-starter process has terminated')
        self._state.value = State.SHUTDOWN

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()

    @property
    def bound_address(self):
        return self._bound_address