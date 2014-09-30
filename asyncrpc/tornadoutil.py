__author__ = 'basca'


def format_info(info):
    return info[info.find("<dt>") + 4: info.find("</dt>")]


def format_args(key, value):
    return value[1:] if key == 'args' else value


def format_description(info):
    return ', '.join(
        list(info['args'])[1:] +
        (['*args'] if info['varargs'] else []) +
        (['**kwargs'] if info['keywords'] else []))

def format_class(instance):
    return str(type(instance))[1:-1].replace("'", "").replace("class ","")