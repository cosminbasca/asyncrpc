__author__ = 'Cosmin Basca'
__email__ = 'basca@ifi.uzh.ch; cosmin.basca@gmail.com'

from setuptools import setup, find_packages

str_version = None
execfile('geventutil/__version__.py')

pip_deps = [
    'nose>=1.3.0',
    'rednose>=0.3',
]

manual_deps = [

]

setup(
    name='geventutil',
    version=str_version,
    description='utilitarian module which provides more gevent goodies',
    author='Cosmin Basca',
    author_email='basca@ifi.uzh.ch',
    packages = ["geventutil", "geventutil/test"],
    include_package_data = True,
    exclude_package_data = {
        'geventutil': ['*.log', '*.log.*']
    },
    zip_safe = False,
    install_requires=manual_deps + pip_deps,
    scripts=[
        # 'scripts/?.py',
    ],
)