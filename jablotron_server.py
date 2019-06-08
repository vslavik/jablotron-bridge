#!/usr/bin/env python3
#
# Copyright (C) 2018-2019 Vaclav Slavik
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
