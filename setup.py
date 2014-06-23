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
    # exclude_package_data = {
    #     'geventmanager': ['*.log', '*.log.*']
    # },
    zip_safe = False,
    install_requires=manual_deps + pip_deps,
    scripts=[
        # 'scripts/?.py',
    ],
)