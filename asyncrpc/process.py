from multiprocessing import Pipe, Process
from multiprocessing.managers import State
from multiprocessing.util import Finalize
import socket
import errno
import signal
from gevent import reinit
from gevent.monkey import patch_all
import psutil
from asyncrpc.exceptions import InvalidStateException
from asyncrpc.log import get_logger
from asyncrpc.server import RpcServer
from asyncrpc.client import dispatch
from asyncrpc.wsgi import Command
from time import sleep

__author__ = 'basca'

# ----------------------------------------------------------------------------------------------------------------------
#
# Background server runner
#
# ----------------------------------------------------------------------------------------------------------------------
class BackgroundRunner(object):
    public = ['start', 'stop', 'restart', 'bound_address', 'dispatch', 'is_running']

    def __init__(self, server_class=None, address=('127.0.0.1', 0), gevent_patch=False, retries=2000):
        if not issubclass(server_class, RpcServer):
            raise ValueError('server_class must be a subclass of RpcServer')

        self._address = address if address else ('127.0.0.1', 0)
        self._server_class = server_class

        self._gevent_patch = gevent_patch
        self._retries = retries
        self._state = State()
        self._state.value = State.INITIAL
        self._process = None
        self._bound_address = None

        self._stop = lambda: None

        self._log = get_logger(server_class.__name__)

    def _background_start(self, writer, **kwargs):
        try:
            if self._gevent_patch:
                reinit()
                patch_all()
            server = None

            retries = 0
            while retries < self._retries:
                try:
                    server = self._server_class(self._address, **kwargs)
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
                server.start()
            else:
                writer.close()
        except Exception, err:
            self._log.error(
                'Rpc server exited. {0}'.format('Exception on exit: {0}'.format(err if err.message else '')))

    def start(self, wait=True, *args, **kwargs):
        if self._state.value != State.INITIAL:
            raise InvalidStateException('server starter has already been initialized')

        reader, writer = Pipe(duplex=False)
        self._process = Process(target=self._background_start, args=(writer,) + args, kwargs=kwargs)
        self._process.name = type(self).__name__ + '-' + self._process.name
        self._log.debug('starting background process: {0}'.format(self._process.name))
        self._process.start()

        writer.close()
        self._bound_address = reader.recv()
        reader.close()
        self._log.info('server starting on {0}'.format(self._bound_address))
        self._log.info('server initialized dispatcher')
        self._stop = Finalize(self, self._finalize, args=(), exitpriority=0)

        if wait:
            while True:
                try:
                    if self._process.is_alive():
                        self._log.info("server process started, waiting for initialization ... ")
                        dispatch(self._bound_address, Command.PING)
                        self._state.value = State.STARTED
                        self._log.info('server started OK')
                        return True
                    else:
                        return False
                except Exception, e:
                    self._log.error("error: {0}".format(e))
                    sleep(0.01)
            return False
        return True

    def restart(self, wait=None):
        self._log.debug('restart')
        self._stop()
        self._state.value = State.INITIAL
        self.start(wait=wait)
        self._log.debug('restarted')

    def stop(self):
        self._stop()

    def _signal_children(self, signals=(signal.SIGINT, signal.SIGUSR1)):
        pid = self._process.pid
        proc = psutil.Process(pid)
        kids = proc.get_children(recursive=False)
        if len(kids):
            self._log.info('signaling {0} request child processes'.format(len(kids)))
            for kid in kids:
                try:
                    self._log.info('\t signal request process [{0}]'.format(kid.pid))
                    for sig in signals:
                        kid.send_signal(sig)
                except psutil.NoSuchProcess:
                    self._log.error('\t process [{0}] no longer exists (skipping)'.format(kid.pid))
        else:
            self._log.info('no child processes to signal on stop')

    # noinspection PyBroadException
    def _finalize(self):
        if not self._process:
            return

        if self._process.is_alive():
            self._signal_children()
            self._process.join(timeout=0.1)
            if not self._process.is_alive():
                return

            self._log.info('sending shutdown message to server')
            try:
                dispatch(self._bound_address, Command.SHUTDOWN)
            except Exception:
                pass

            self._log.info('wait for server-starter process to terminate')
            self._process.join(timeout=10.0)

            if self._process.is_alive():
                self._log.info('server-starter still alive')
                if hasattr(self._process, 'terminate'):
                    self._log.info('trying to `terminate()` manager process')
                    self._process.terminate()
                    self._process.join(timeout=10.0)
                    if self._process.is_alive():
                        self._log.warn('server-starter still alive after terminate!')
            else:
                self._log.info('server-starter process has terminated')
        self._state.value = State.SHUTDOWN

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._stop()

    @property
    def bound_address(self):
        return self._bound_address

    @property
    def is_running(self):
        return self._state.value == State.STARTED