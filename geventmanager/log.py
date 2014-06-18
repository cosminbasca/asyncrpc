import logging

__all__ = ['get_logger']

__author__ = 'basca'

# see more @ http://victorlin.me/posts/2012/08/26/good-logging-practice-in-python
logging.config.fileConfig('logging.ini')

def get_logger(name):
    return logging.getLogger(name)