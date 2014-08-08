from inspect import isclass
import logging
from logging.config import fileConfig
import os

__all__ = ['get_logger', 'logger', 'ClassLogger', 'module_name']

__author__ = 'basca'

__levels__ = {
    'debug': logging.DEBUG,
    'info': logging.INFO,
    'warning': logging.WARNING,
    'error': logging.ERROR,
    'critical': logging.CRITICAL,
}


def module_name():
    return os.path.split(os.path.dirname(os.path.abspath(__file__)))[-1]


class ClassLogger(logging.Logger):
    def __init__(self, name, level=logging.NOTSET):
        super(ClassLogger, self).__init__(name, level=level)
        self._owner_class = None

    def set_owner(self, owner):
        if not isclass(owner):
            owner = owner.__class__
        if not isclass(owner):
            raise ValueError('owner must be a class, got {0} instead'.format(owner))
        self._owner_class = owner

    def _log(self, level, msg, args, exc_info=None, extra=None):
        if self._owner_class:
            msg = '{0}: {1}'.format(self._owner_class.__name__, msg)
        return super(ClassLogger, self)._log(level, msg, args, exc_info=exc_info, extra=extra)


logging.setLoggerClass(ClassLogger)
fileConfig(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logging.ini'))


def get_logger(name=None, owner=None):
    if not name:
        name = module_name()
    class_logger = logging.getLogger(name)
    if isinstance(class_logger, ClassLogger) and owner:
        class_logger.set_owner(owner)
    return class_logger


def set_level(level, name=None, default=logging.WARNING):
    if isinstance(level, basestring):
        level = __levels__.get(level, default)
    current_logger = logging.getLogger(name) if name else logging.root
    current_logger.setLevel(level)


logger = get_logger()