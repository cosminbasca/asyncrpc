__author__ = 'Cosmin Basca'
__email__ = 'basca@ifi.uzh.ch; cosmin.basca@gmail.com'

from setuptools import setup, find_packages

str_version = None
execfile('msgpackutil/__version__.py')

pip_deps = [
    'msgpack-python>=0.4.2',
    'numpy>=1.8.0',
    'pandas>=0.13.0',
    'nose>=1.3.0',
    'rednose>=0.3',
]

manual_deps = [

]

setup(
    name='msgpackutil',
    version=str_version,
    description='utilitarian module which provides support for serializing and deserializing hooks for msgpack',
    author='Cosmin Basca',
    author_email='basca@ifi.uzh.ch',
    packages = ["msgpackutil", "msgpackutil/hooks", "msgpackutil/test"],
    # package_dir = {"msgpackutil":"msgpackutil"},
    include_package_data = True,
    exclude_package_data = {
        'msgpackutil': ['*.log', '*.log.*']
    },
    zip_safe = False,
    install_requires=manual_deps + pip_deps,
    scripts=[
        # 'scripts/?.py',
    ],
)