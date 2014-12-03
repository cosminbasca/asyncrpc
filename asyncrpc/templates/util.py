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
__author__ = 'basca'


def format_info(info):
    return info[2][info[2].find("<dt>") + 4: info[2].find("</dt>")]


def format_args(key, value):
    return value[1:] if key == 'args' else value


def format_description(info):
    return ', '.join(
        list(info[1]['args'])[1:] +
        (['*args'] if info[1]['varargs'] else []) +
        (['**kwargs'] if info[1]['keywords'] else []))

def format_class(instance):
    return str(type(instance))[1:-1].replace("'", "").replace("class ","")

def async_method_class(info):
    # return 'warning' if info[0] else ''
    return 'info' if info[0] else ''