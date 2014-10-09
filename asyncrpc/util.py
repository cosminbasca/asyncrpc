__author__ = 'basca'

__types_list = (list, tuple)
__types_str = (str, unicode)


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
        elif size >=2 and isinstance(address[1], __types_str):
            return map(format_address, address)
    return format_address(address)
