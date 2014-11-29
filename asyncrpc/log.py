from frozendict import frozendict
import logging

__author__ = 'basca'

DISABLED = logging.CRITICAL + 100

logging_levels = frozendict({
    'debug': logging.DEBUG,
    'info': logging.INFO,
    'warning': logging.WARNING,
    'error': logging.ERROR,
    'critical': logging.CRITICAL,
    'disabled': DISABLED,
})


def set_logger_level(level, name=None, default='error'):
    if isinstance(level, basestring):
        level = logging_levels.get(level, logging_levels[default])
    current_logger = logging.getLogger(name) if name else logging.root
    current_logger.setLevel(level)


def disable_logger(name=None):
    current_logger = logging.getLogger(name) if name else logging.root
    current_logger.setLevel(logging.CRITICAL + 100)  # this disables logging effectivelly
