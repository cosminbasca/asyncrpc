__author__ = 'basca'


def format_address(address):
    if isinstance(address, (tuple, list)):
        host, port = address
    elif isinstance(address, (str, unicode)):
        host, port = address.split(':')
        port = int(port)
    else:
        raise ValueError('address, must be either a tuple/list or string of the name:port form')
    return host, port


def format_addresses(address):
    if isinstance(address, (tuple, list)) and isinstance(address[0], (list, tuple)):
        return map(format_address, address)
    return format_address(address)
