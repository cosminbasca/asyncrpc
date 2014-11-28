from inspect import isclass
import logging
import os
import sys
from logbook import Logger
from frozendict import frozendict

__author__ = 'basca'

logging_levels = frozendict({
    'debug': logging.DEBUG,
    'info': logging.INFO,
    'warning': logging.WARNING,
    'error': logging.ERROR,
    'critical': logging.CRITICAL,
})


def get_logger(group=None, owner=None, level='critical'):
    name = None
    if isinstance(owner, basestring):
        name = '{0}.{1}'.format(group, owner) if isinstance(group, basestring) else owner
    elif owner:
        group = owner.__module__
        if group == '__main__':
            group = os.path.splitext(os.path.basename(sys.modules[group].__file__))[0]
        name = '{0}.{1}'.format(group, owner.__name__ if isclass(owner) else owner.__class__.__name__)
    return Logger(name, level=level)

def set_logging_level(level, name=None, default='error'):
    if isinstance(level, basestring):
        level = logging_levels.get(level, logging_levels[default])
    current_logger = logging.getLogger(name) if name else logging.root
    current_logger.setLevel(level)


def disable_logging(name=None):
    current_logger = logging.getLogger(name) if name else logging.root
    current_logger.setLevel(logging.CRITICAL + 100)  # this disables logging effectivelly


logger = get_logger(sys.modules[__name__])