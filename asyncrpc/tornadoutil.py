__author__ = 'basca'


def format_info(info):
    return info[2][info[2].find("<dt>") + 4: info[2].find("</dt>")]


def format_args(key, value):
    return value[1:] if key == 'args' else value


def format_description(info):
    return ', '.join(
        list(info[1]['args'])[1:] +
        (['*args'] if info[1]['varargs'] else []) +
        (['**kwargs'] if info[1]['keywords'] else []))

def format_class(instance):
    return str(type(instance))[1:-1].replace("'", "").replace("class ","")

def async_method_class(info):
    return 'warning' if info[0] else ''