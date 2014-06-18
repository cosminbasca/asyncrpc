#!/bin/bash
clear
echo "install dependencies ... "
pip install -r "./dependencies.txt"
echo "testing geventutil ..."
nosetests --rednose -v -s ./geventutil/test/
echo "building module egg distribution ... "
python setup.py bdist_egg
echo "building source distribution ... "
python setup.py sdist --formats=gztar

echo "all done!"