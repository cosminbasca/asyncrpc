from geventmanager.log import get_logger
from geventmanager.proxy import InetProxy, GeventProxy, GeventPooledProxy, Dispatcher
from geventmanager.server import PreforkedRpcServer, ThreadedRpcServer
from multiprocessing.managers import State

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
            instance_id = self._dispatch('#INIT', *args, **kwargs)
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
                 preforked=False, **kwargs):
        self._log = get_logger(self.__class__.__name__)

        self._process = None
        self._address = address if address else ('127.0.0.1', 0)
        self._state = State()
        self._state.value = State.INITIAL

        self._async = async
        self._async_pooled = async_pooled
        self._gevent_patch = gevent_patch
        self._pool_concurrency = pool_concurrency

        self._Server = PreforkedRpcServer if preforked else ThreadedRpcServer
        self._log.debug('manager using [{0}] server'.format(self._Server.__name__))


    def _run_server(self, HandlerClass, host, writer, h_args=(), h_kwargs={}, srv_kwargs={}, gevent_patch=False):
        """ Create a server, report its address and run it """
        _host = host
        try:
            if gevent_patch:
                reinit()
                patch_all()
            server = None
            rpc_handler = HandlerClass(*h_args, **h_kwargs)

            retries = 0
            while retries < _RETRIES:
                try:
                    server = self._Server(_host, rpc_handler, **srv_kwargs)
                    break
                except socket.timeout:
                    retries -= 1
                except socket.error, err:
                    if type(err.args) != tuple \
                            or err[0] not in [errno.ETIMEDOUT, errno.EAGAIN, errno.EADDRINUSE]:
                        raise
                    retries -= 1

            if server:
                writer.send(server.address)
                writer.close()
                server.run()
            else:
                writer.close()
        except Exception, err:
            self._log_message('the RPC server exited. %s' % ('Exception on exit: %s' % err if err.message else ''))


    def dispatch_command(self, command):
        proxy = InetProxy(self._host)
        return getattr(proxy, command)()

    def shutdown_server(self):
        return self.dispatch_command(RPCCommand.SHUTDOWN)

    def ping_server(self):
        return self.dispatch_command(RPCCommand.PING)

    def start(self, wait=True):
        """ start server in a different process (avoid blocking the main thread due to the servers event loop ) """
        assert self._state.value == State.INITIAL, '[rpc manager] has allready been initialized'

        reader, writer = Pipe(duplex=False)

        self._process = Process(target=self._run_server, args=(self._RpcHandler, self._host, writer),
                                kwargs={
                                    'h_args': self._handler_args,
                                    'h_kwargs': self._handler_kwargs,
                                    'srv_kwargs': self._kwargs,
                                    'gevent_patch': self._gevent_patch if self._async else False
                                })

        ident = ':'.join(str(i) for i in self._process._identity)
        self._process.name = type(self).__name__ + '-' + ident
        self._process.start()

        writer.close()
        self._host = reader.recv()
        reader.close()
        self._log_message('server starting on %s:%s' % (self._host.name, self._host.port))

        self.shutdown = Finalize(self, self._finalize, args=(), exitpriority=0)

        if wait:
            while True:
                try:
                    if self._process.is_alive():
                        self.ping_server()
                        self._log_message('server started OK')
                        self._state.value = State.STARTED
                        return True
                    else:
                        return False
                except:
                    sleep(0.01)
            return False
        return True

    def restart(self, wait=None):
        self.debug('restart')
        self.shutdown()
        self._state.value = State.INITIAL
        self.start(wait=True)
        self.debug('restarted')

    def stop(self):
        self.shutdown()

    def get_proxy(self):
        return self._Proxy(self._host, concurrency=self._concurrency)

    proxy = property(fget=get_proxy)

    def _signal_children(self):
        pid = self._process.pid
        proc = psutil.Process(pid)
        kids = proc.get_children(recursive=False)
        self.debug('signaling %s request child processes' % len(kids))
        for kid in kids:
            try:
                self.debug('\tsignal request process [%s]' % kid.pid)
                kid.send_signal(signal.SIGUSR1)
            except psutil.NoSuchProcess:
                self.error('\tprocess [%s] no longer exists (skipping)' % kid.pid)

    # noinspection PyBroadException
    def _finalize(self):
        """ Shutdown the manager process; will be registered as a finalizer """
        if not self._process:
            return

        if self._process.is_alive():
            self._signal_children()

            self.debug('sending shutdown message to server')
            try:
                self.shutdown_server()
            except Exception:
                pass

            self.debug('wait for server-starter process to terminate')
            self._process.join(timeout=_SHUTDOWN_WAIT)

            if self._process.is_alive():
                self.debug('manager still alive')
                if hasattr(self._process, 'terminate'):
                    self.debug('trying to `terminate()` manager process')
                    self._process.terminate()
                    self._process.join(timeout=_SHUTDOWN_WAIT)
                    if self._process.is_alive():
                        self.debug('manager still alive after terminate!')
            else:
                self.debug('server-starter process has terminated')
        self._state.value = State.SHUTDOWN

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()

    host = property(fget=lambda self: self._host)