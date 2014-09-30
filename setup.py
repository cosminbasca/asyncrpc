#!/usr/bin/env python

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
with open('README') as f:
    DESCRIPTION = f.read()

pip_deps = [
    'gevent>=1.0.1',
    'nose>=1.3.0',
    'rednose>=0.3',
    'psutil>=2.1.1',
    'requests>=2.3.0',
    'geventhttpclient>=1.1',
    'cherrypy>=3.5.0',
    'Werkzeug>=0.9.6',
    'Jinja2>=2.7.3',
    'retrying>=1.2.2',
    'docutils>=0.12',
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
    packages=[NAME, '{0}/test'.format(NAME)],
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
