__author__ = 'Cosmin Basca'
__email__ = 'basca@ifi.uzh.ch; cosmin.basca@gmail.com'

from setuptools import setup, find_packages

str_version = None
execfile('geventmanager/__version__.py')

pip_deps = [
    'gevent>=1.0.1',
    'geventhttpclient>=1.1',
    'nose>=1.3.0',
    'rednose>=0.3',
    'psutil>=2.1.1',
    'py-prefork-server>=0.2.2',
    'requests>=2.3.0',
    'grequests>=0.2.0',
    'cherrypy>=3.5.0',
]

manual_deps = [
    'msgpackutil>=0.1.12'
]

setup(
    name='geventmanager',
    version=str_version,
    description='a gevent manager similar to the multiprocessing manager',
    author='Cosmin Basca',
    author_email='basca@ifi.uzh.ch',
    packages = ["geventmanager", "geventmanager/test"],
    include_package_data = True,
    zip_safe = False,
    install_requires=manual_deps + pip_deps,
    scripts=[
        # 'scripts/?.py',
    ],
)