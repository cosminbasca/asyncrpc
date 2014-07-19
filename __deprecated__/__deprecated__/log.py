import logging

__author__ = 'basca'

__levels__ = {
    'debug': logging.DEBUG,
    'info': logging.INFO,
    'warning': logging.WARNING,
    'error': logging.ERROR,
    'critical': logging.CRITICAL,
}


def enable_root_logger():
    logging.root.disabled = False


def disable_root_logger():
    logging.root.disabled = True

# by default, root logger disabled!
disable_root_logger()

logger = logging.getLogger('avarpc')
ava_handler = logging.StreamHandler()
ava_formatter = logging.Formatter("%(asctime)s - [%(levelname)s] - %(message)s", "%H:%M:%S")
ava_handler.setFormatter(ava_formatter)
logger.addHandler(ava_handler)
logger.propagate = 0
logger.setLevel(__levels__.get('debug', logging.WARNING))


class LoggerMixin(object):
    _logger = logger

    def _message_formatter(self, message):
        return str(message)

    def _log_message(self, message, msg_type=logging.INFO):
        if self._logger:
            self._logger.log(msg_type, '[%s] %s' % (self.__class__.__name__, self._message_formatter(message)))
        else:
            print '[%s] %s' % (self.__class__.__name__, self._message_formatter(message))

    def info(self, message):
        self._log_message(message, msg_type=logging.INFO)

    def warn(self, message):
        self._log_message(message, msg_type=logging.WARNING)

    def debug(self, message):
        self._log_message(message, msg_type=logging.DEBUG)

    def error(self, message):
        self._log_message(message, msg_type=logging.ERROR)


