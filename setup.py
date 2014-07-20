#!/usr/bin/env python

try:
    from setuptools import setup
except ImportError:
    from ez_setup import use_setuptools

    use_setuptools()
    from setuptools import setup

import os

str_version = None
execfile('asyncrpc/__version__.py')

NAME = 'asyncrpc'

# Load up the description from README
with open('README') as f:
    DESCRIPTION = f.read()

pip_deps = [
    'gevent>=1.0.1',
    'nose>=1.3.0',
    'rednose>=0.3',
    'psutil>=2.1.1',
    'py-prefork-server>=0.2.2',
    'requests>=2.3.0',
    'grequests>=0.2.0',
    'cherrypy>=3.5.0',
    'Werkzeug>=0.9.6',
    'Jinja2>=2.7.3',
    'retrying>=1.2.2',
]

manual_deps = [
    'msgpackutil>=0.1.12'
]

setup(
    name=NAME,
    version=str_version,
    author='Cosmin Basca',
    author_email='cosmin.basca@gmail.com; basca@ifi.uzh.ch',
    # url=None,
    description='A http rpc library, providing a manager similar to the '
                'multiprocessing.Basemanager with gevent support',
    long_description=DESCRIPTION,
    classifiers=[
        'Intended Audience :: Developers',
        # 'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: JavaScript',
        'Topic :: Software Development'
    ],
    packages=['asyncrpc', 'asyncrpc/test'],
    package_data={
        'asyncrpc': ['static/*.ico',
                     'static/*.js',
                     'static/bootstrap/js/*.js',
                     'static/bootstrap/css/*.css',
                     'static/bootstrap/img/*.png',
                     'static/bootstrap.386/js/*.js',
                     'static/bootstrap.386/css/*.css',
                     'static/bootstrap.386/img/*.png',
                     'static/tooltip/*.js',
                     'static/tooltip/*.css',
                     'templates/*.html']
    },
    install_requires=manual_deps + pip_deps,
    entry_points={
        # 'console_scripts': ['asyncrpc = asyncrpc.cli:main']
    }
)
