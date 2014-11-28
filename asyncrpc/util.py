import os

__author__ = 'basca'

__types_list = (list, tuple)
__types_str = (str, unicode)
__types_all = __types_str + __types_list


def format_address(address):
    if isinstance(address, __types_str):
        host, port = address.split(':')
        port = int(port)
    elif isinstance(address, __types_list):
        host, port = address
    else:
        raise ValueError('address, must be either a tuple/list or string of the name:port form')
    return host, port


def format_addresses(address):
    if isinstance(address, __types_list):
        size = len(address)
        if size == 1:
            return format_address(address[0])
        elif size >= 2 and isinstance(address[1], __types_all):
            return map(format_address, address)
    return format_address(address)


__templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
__static_dir = os.path.join(os.path.dirname(__file__), 'static')


def get_templates_dir():
    global __templates_dir
    return __templates_dir


def get_static_dir():
    global __static_dir
    return __static_dir
