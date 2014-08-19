__author__ = 'cosmin'

from docutils.core import publish_string, publish_parts

src = """more complex
    :param a: val a
    :param b: val b
    :param val: val val
    :param val2: val val2
    :param kwargs: other
    :return: None"""

print publish_parts(src.strip(), writer_name='html')['fragment']