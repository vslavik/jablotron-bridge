#!/usr/bin/env python3
#
# Copyright (c) 2018-2019 Václav Slavík
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#

import logging
import sys
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


def get_sensor_kind(model: str):
    if model.endswith('M'):
        return 'window'
    if model.endswith('P'):
        return 'motion'
    if model.endswith('B'):
        return 'glassbreak'
    if model.endswith('A'):  # alarms/sirens
        return 'ignore'
    if model.endswith('E'):  # entry keypads
        return 'ignore'
    if model.endswith('R'):  # radio modules
        return 'ignore'
    if model == 'JA-121T':  # RS-485 interface
        return 'ignore'
    if (model.startswith('JA-100K') or model.startswith('JA-101K') or
            model.startswith('JA-106K')):  # control panel
        return 'ignore'
    return None


data = ET.parse(sys.argv[1])
print('sensors = [')
for row in data.findall('./table2/row'):
    sid = int(row.find('position').text)
    name = row.find('name').text
    model = row.find('type').text
    kind = get_sensor_kind(model)
    if kind is None:
        logger.warning('  # Warning: omitting sensor of unrecognized kind:')
        print('  # {{ id = {:2}, model = "{}", name = "{}" }},'.format(sid, model, name))
        continue
    elif kind == 'ignore':
        continue
    else:
        section = row.find('section').text
        note = row.find('note').text
        print('  {{ id = {:2}, model = "{}", kind = "{}", name = "{}" }},'.format(sid, model, kind, name))
print(']')
