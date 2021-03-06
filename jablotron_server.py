#!/usr/bin/env python3
#
# Copyright (c) 2018-2020 Václav Slavík
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

import jablotron.core
import jablotron.homekit

import asyncio
import logging
import signal


logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)
logging.getLogger('pyhap.hap_server').setLevel(logging.WARNING)


loop = asyncio.get_event_loop()

alarm = loop.run_until_complete(jablotron.core.create_connection(loop, 'jablotron.toml'))
homekit = jablotron.homekit.create_driver(loop, alarm)

signal.signal(signal.SIGINT, homekit.signal_handler)
signal.signal(signal.SIGTERM, homekit.signal_handler)
homekit.start()
