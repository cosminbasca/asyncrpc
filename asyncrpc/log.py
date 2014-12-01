__author__ = 'basca'

LOGGER_NAME = 'asyncrpc'

_logger = None

DISABLED = 100
CRITICAL = 50
ERROR = 40
WARNING = 30
INFO = 20
DEBUG = 10
NOTSET = 0


def debug(msg, *args):
    if __debug__:
        if _logger:
            _logger.log(DEBUG, msg, *args)


def info(msg, *args):
    if _logger:
        _logger.log(INFO, msg, *args)


def warn(msg, *args):
    if _logger:
        _logger.log(WARNING, msg, *args)


def error(msg, *args):
    if _logger:
        _logger.log(ERROR, msg, *args)


def get_logger(name=LOGGER_NAME, handler=None):
    import logging

    LOG_FORMAT = '%(asctime)s %(levelname)-8s %(name)-15s %(message)s'
    logging._acquireLock()
    try:
        # general setup
        formatter = logging.Formatter(LOG_FORMAT)

        if not handler:
            handler = [logging.StreamHandler()]
        elif not isinstance(handler, (list, tuple)):
            handler = [handler]

        logger = logging.getLogger(name)
        logger.propagate = 0
        for hndlr in handler:
            hndlr.setFormatter(formatter)
            logger.addHandler(hndlr)
    finally:
        logging._releaseLock()

    return logger


def setup_logger(name=LOGGER_NAME, handler=None):
    global _logger
    _logger = get_logger(name=name, handler=handler)


def uninstall_logger():
    global _logger
    _logger = None


def set_logger_level(level, name=None):
    import logging

    logging._acquireLock()
    try:
        logger = logging.getLogger(name) if name else logging.root
        logger.setLevel(level)
    finally:
        logging._releaseLock()


def disable_logger(name=None):
    set_logger_level(DISABLED, name=name)
