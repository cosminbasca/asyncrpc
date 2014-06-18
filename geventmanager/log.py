import logging

__all__ = ['get_logger']

__author__ = 'basca'

logging.config.fileConfig('logging.ini')

def get_logger(name):
    return logging.getLogger(name)