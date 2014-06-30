from tornado.tcpserver import TCPServer
from tornado.ioloop import IOLoop
from tornado.netutil import bind_sockets

__author__ = 'basca'

# ----------------------------------------------------------------------------------------------------------------------
#
# tornado based preforked tcpserver
#
# ----------------------------------------------------------------------------------------------------------------------
class TornadoRpcServer(TCPServer):
    def __init__(self, registry):
        super(TornadoRpcServer, self).__init__()
        self._stream = None
        self._registry = registry

    def handle_stream(self, stream, address):
        self._stream = stream



# def start(self):
#     _sockets = bind_sockets(self.port, address=self.host)
#     _sock = _sockets[0] if len(_sockets) else _sockets
#     self._bound_address = _sock.getsockname()
#     self._server.add_sockets(_sockets)
#     IOLoop.instance().start()



