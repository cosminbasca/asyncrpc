#
# author: Cosmin Basca
#
# Copyright 2010 University of Zurich
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
from multiprocessing import Pipe, Process, Event
from multiprocessing.managers import State
from multiprocessing.util import Finalize
from threading import Thread
from time import sleep
from gevent import reinit
from gevent.monkey import patch_all
from asyncrpc.exceptions import InvalidStateException, BackgroundRunnerException
from asyncrpc.server import RpcServer, server_is_online
from asyncrpc.log import debug, info, error, warn
import sys
import os
import socket
import errno
import traceback


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
        debug('server address is %s', self._address)
        self._server_class = server_class

        self._gevent_patch = gevent_patch
        self._retries = retries
        self._state = State()
        self._state.value = State.INITIAL
        self._process = None
        self._bound_address = None
        self._shutdown_event = Event()
        self._stop = lambda: None


    # noinspection PyBroadException
    def _background_start(self, writer, shutdown_event, *args, **kwargs):
        try:
            if self._gevent_patch:
                reinit()
                patch_all()
            server = None

            retries = 0
            while retries < self._retries:
                try:
                    server = self._server_class(self._address, *args, **kwargs)
                    break
                except socket.timeout:
                    retries -= 1
                except socket.error, err:
                    if type(err.args) != tuple or err[0] not in [errno.ETIMEDOUT, errno.EAGAIN, errno.EADDRINUSE]:
                        raise
                    retries -= 1
                except Exception:
                    ex_type, ex_class, tb = sys.exc_info()
                    writer.send((ex_type, ex_class, traceback.extract_tb(tb)))
                    writer.close()
                    return

            if server:
                def port_check(_port, _server):
                    debug('started port checker')
                    while _port == _server.bound_address[1]:
                        sleep(0.01)
                    writer.send(_server.bound_address)
                    writer.close()
                    debug('port checker finalized')

                port = self._address[1]
                if port == 0:  # find out the bound port if the initial port is 0
                    debug('port is 0, start waiting thread for bound port ... ')
                    checker = Thread(target=port_check, args=(port, server))
                    checker.daemon = True
                    checker.start()

                def wait_for_shutdown():
                    debug('started server stopper thread')
                    shutdown_event.wait()
                    debug('server shutdown event received')
                    server.stop()
                    os._exit(0)

                stopper = Thread(target=wait_for_shutdown)
                stopper.daemon = True
                stopper.start()

                server.start()
                debug('server shutdown successfully')
            else:
                writer.stop()
        except Exception, err:
            error('Rpc server exited. Exception on exit: %s', err if err.message else '')

    def start(self, wait=True, *args, **kwargs):
        if self._state.value != State.INITIAL:
            raise InvalidStateException('server starter has already been initialized')

        reader, writer = Pipe(duplex=False)
        self._process = Process(target=self._background_start, args=(writer, self._shutdown_event,) + args,
                                kwargs=kwargs)
        self._process.name = ''.join((type(self).__name__, '-', self._process.name))
        debug('starting background process: %s', self._process.name)
        self._process.start()

        debug('started background process with pid: %s', self._process.pid)

        writer.close()
        debug('waiting for bound address .. ')
        response = reader.recv()
        reader.close()
        if isinstance(response, tuple) and len(response) == 3:
            raise BackgroundRunnerException("Exception occured while starting the background server process",
                                            response[0], response[1], response[2])
        self._bound_address = response

        info('server started on %s', self._bound_address)
        self._stop = Finalize(self, type(self)._finalize, args=(self._process, self._shutdown_event, self._state),
                              exitpriority=0)

        if wait:
            max_retries = self._retries
            while True:
                if server_is_online(self._bound_address):
                    self._state.value = State.STARTED
                    info('server started OK')
                    return True
                if max_retries == 0:
                    return False
                sleep(0.01)
                max_retries -= 1
        return True

    def restart(self, wait=None):
        debug('restart')
        self._stop()
        self._state.value = State.INITIAL
        self.start(wait=wait)
        debug('restarted')

    def stop(self):
        self._stop()

    @staticmethod
    def _finalize(process, shutdown_event, state):
        if process.is_alive():
            debug('setting the shutdown event')
            shutdown_event.set()

            debug('wait for server-starter process to terminate')
            process.join(timeout=0.2)

            if process.is_alive():
                debug('server-starter still alive')
                if hasattr(process, 'terminate'):
                    debug('trying to "terminate()" manager process')
                    process.terminate()
                    process.join(timeout=10.0)
                    if process.is_alive():
                        debug('server-starter still alive after terminate!')
            else:
                debug('server-starter process has terminated')
        state.value = State.SHUTDOWN

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