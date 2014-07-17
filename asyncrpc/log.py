import logging
from logging.config import fileConfig
import os

__all__ = ['get_logger']

__author__ = 'basca'

# see more @ http://victorlin.me/posts/2012/08/26/good-logging-practice-in-python
fileConfig(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logging.ini'))


def get_logger(name):
    return logging.getLogger(name)

__levels__ = {
    'debug': logging.DEBUG,
    'info': logging.INFO,
    'warning': logging.WARNING,
    'error': logging.ERROR,
    'critical': logging.CRITICAL,
}

def set_level(level, default=logging.WARNING):
    if isinstance(level, basestring):
        level = __levels__.get(level, default)
    logging.root.setLevel(level)