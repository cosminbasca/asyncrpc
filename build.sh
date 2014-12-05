#!/bin/bash
clear
echo "install dependencies ... "
pip install -r "./requirements.txt"
echo "testing asyncrpc ..."
nosetests --rednose -v -s ./asyncrpc/test/
echo "building module egg distribution ... "
python setup.py bdist_egg
echo "building source distribution ... "
python setup.py sdist --formats=gztar
echo "all done"