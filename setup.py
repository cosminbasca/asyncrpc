#!/usr/bin/env python
#
# author: Cosmin Basca
#
# Copyright 2010 University of Zurich
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
try:
    from setuptools import setup
except ImportError:
    from ez_setup import use_setuptools

    use_setuptools()
    from setuptools import setup

NAME = 'asyncrpc'

str_version = None
execfile('{0}/__version__.py'.format(NAME))

# Load up the description from README
with open('README.md') as f:
    DESCRIPTION = f.read()

pip_deps = [
    'gevent>=1.0.1',
    'geventhttpclient>=1.1',
    'nose>=1.3.0',
    'rednose>=0.3',
    'psutil>=2.1.3',
    'requests>=2.4.3',
    'cherrypy>=3.6.0',
    'Werkzeug>=0.9.6',
    'Jinja2>=2.7.3',
    'retrying>=1.3.2',
    'docutils>=0.12',
]

manual_deps = []

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
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: JavaScript',
        'Topic :: Software Development'
    ],
    packages=[
        NAME,
        '{0}/templates'.format(NAME),
        '{0}/test'.format(NAME),
    ],
    package_data={
        NAME: ['static/*.ico',
               'static/js/*.*',
               'static/docutils/*.*',
               'static/bootstrap/js/*.*',
               'static/bootstrap/css/*.*',
               'static/bootstrap/fonts/*.*',
               'templates/*.*',
               '*.ini']
    },
    install_requires=manual_deps + pip_deps,
    entry_points={
        # 'console_scripts': ['asyncrpc = asyncrpc.cli:main']
    }
)
