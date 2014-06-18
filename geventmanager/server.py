__author__ = 'basca'


def _command(name):
    return '#cmd:{0}#'.format(name)


_CMD_SHUTDOWN = _command('shutdown')
_CMD_PING = _command('ping')
_CMD_CLOSE_CONN = _command('close_conn')
_INIT_ROBJ = _command('init_robj')

