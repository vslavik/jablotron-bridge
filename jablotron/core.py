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

import asyncio
import binascii
import collections
import logging
import serial_asyncio
import toml
import re
import threading
import weakref


logger = logging.getLogger(__name__)


class Sensor:
    """
    """
    MOTION = 'motion'
    WINDOW = 'window'
    OTHER  = 'other'

    def __init__(self, alarm, config):
        self.homekit = None
        self.alarm = weakref.proxy(alarm)
        self.id = config['id']
        self.name = config.get('name', 'Sensor %d' % self.id)
        self.model = config.get('model', None)
        kind = config.get('kind', None)
        self.kind = kind if kind in [Sensor.MOTION, Sensor.WINDOW] else Sensor.OTHER
        self._value = False

    def __str__(self):
        return 'sensor #%d (%s) "%s"' % (self.id, self.kind, self.name)

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        if self._value == value:
            return
        self._value = value
        if self.homekit:
            self.homekit.update(value)



SECTION_DISARMED = 'READY'
SECTION_ARMED = 'ARMED'
SECTION_PARTIALLY_ARMED = 'ARMED_PART'
_known_section_states = [SECTION_DISARMED, SECTION_ARMED, SECTION_PARTIALLY_ARMED]

# builtin states:
STATE_DISARMED = 'disarmed'
STATE_HOME = 'home'
STATE_NIGHT = 'night'
STATE_AWAY = 'away'
STATE_TRIGGERED = 'triggered'


class AlarmState:
    """Describe state of alarm in terms of its sections."""
    def __init__(self, name, armed=[], partial=[]):
        self.name = name
        self.sections = {}
        for s in armed:
            self.sections[s] = SECTION_ARMED
        for s in partial:
            self.sections[s] = SECTION_PARTIALLY_ARMED

    def get_sections(self, state):
        for s, sst in self.sections.items():
            if sst == state:
                yield s

    def matches(self, sections):
        for s, state in self.sections.items():
            if sections.get(s, SECTION_DISARMED) != state:
                return False
        for s, state in sections.items():
            if self.sections.get(s, SECTION_DISARMED) != state:
                return False
        return True


def response_handler(regex):
    """Decorator for RS-485 response handlers"""

    def decorator(fn):
        fn._regex = regex
        return fn

    return decorator


class JablotronRS485(asyncio.Protocol):
    """
    """
    def __init__(self, loop, config_file):
        self.update_lock = threading.Lock()
        self.homekit = None
        self.config = toml.load(config_file)
        self.pin = self.config['pin']
        self.firmware_version = None
        self.hardware_version = None
        self.serial_number = None
        self.model = None
        self.sensors = {s['id']: Sensor(self, s) for s in self.config.get('sensors', [])}
        self.section_states = {}
        self.states = collections.OrderedDict()
        self.states[STATE_DISARMED] = AlarmState(STATE_DISARMED)
        for s in self.config['states']:
            st = AlarmState(s['name'], armed=s.get('armed', []), partial=s.get('partial', []))
            self.states[st.name] = st
            for sec in st.sections:
                self.section_states[sec] = STATE_DISARMED
        self.current_state = STATE_DISARMED
        self.current_state_pending = False
        self.event_loop = loop
        self.recognized_response_event = asyncio.Event(loop=loop)
        self.initialized_event = asyncio.Event(loop=loop)
        self.active_sensors = set()
        self.transport = None
        self.buffer = ''
        self._responses_map = {}
        for fn in (getattr(self, x) for x in dir(self)):
            if callable(fn):
                regex = getattr(fn, '_regex', None)
                if regex:
                    self._responses_map[re.compile('^{}$'.format(regex))] = fn

    def connection_made(self, transport):
        logger.info('RS-485 connection established')
        self.buffer = ''
        self.transport = transport
        self.recognized_response_event = asyncio.Event(loop=transport.loop)
        asyncio.async(self._get_initial_state())

    async def _get_initial_state(self):
        await self.send_command('VER')
        await self.send_command('PRFSTATE')
        await self.send_command('STATE')
        self.initialized_event.set()

    def data_received(self, data):
        self.buffer += data.decode('ascii', errors='replace')
        while True:
            split_in_two = re.split('[\r\n\ufffd]+', self.buffer, 1)
            if len(split_in_two) == 1:
                break
            line, self.buffer = split_in_two
            self.line_received(line)

    async def send_command(self, text):
        logger.info(' → %s', repr(text))
        self.recognized_response_event.clear()
        self.transport.write(text.encode() + b'\n')
        await self.recognized_response_event.wait()

    async def send_authenticated_command(self, text):
        await self.send_command('{} {}'.format(self.pin, text))

    async def _do_set_alarm_state(self, state):
        state = self.states[state]
        logger.info('setting alarm to: %s (%s)', state.name, state.sections)
        arm = set(state.get_sections(SECTION_ARMED))
        arm_partially = set(state.get_sections(SECTION_PARTIALLY_ARMED))
        disarm = set(self.section_states.keys()) - arm - arm_partially

        if disarm:
            await self.send_authenticated_command('UNSET {}'.format(' '.join(str(x) for x in disarm)))
        if arm:
            await self.send_authenticated_command('SET {}'.format(' '.join(str(x) for x in arm)))
        if arm_partially:
            await self.send_authenticated_command('SETP {}'.format(' '.join(str(x) for x in arm_partially)))

    def set_alarm_state(self, state):
        asyncio.run_coroutine_threadsafe(self._do_set_alarm_state(state), self.event_loop)

    def line_received(self, line):
        logger.info(' ← %s', repr(line))
        if not line:
            return
        for regex, fn in self._responses_map.items():
            m = regex.match(line)
            if m:
                fn(*m.groups())
                self.recognized_response_event.set()
                return
        logger.warning('unrecognized response %s, ignoring', repr(line))
        self.recognized_response_event.set()

    @response_handler(r'OK|STATE:')
    def on_unimportant(self):
        pass

    @response_handler(r'OK')
    def on_ok(self):
        # TODO: note last update time
        pass

    # JA-121T, SN:1210037d, SWV:NN60202, HWV:1
    @response_handler(r'([^,]+), SN:(.*), SWV:(.*), HWV:(.*)')
    def on_version(self, model, sn, swv, hwv):
        self.model = model
        self.serial_number = sn
        self.firmware_version = swv
        self.hardware_version = hwv

    @response_handler(r'STATE ([0-9]+) (READY|ARMED_PART|ARMED|SERVICE|BLOCKED|OFF)')
    def on_state(self, section, state):
        section = int(section)
        logger.info('section %d reported state "%s"', section, state)
        if state in _known_section_states:
            self.section_states[section] = state
            if not self.current_state_pending:
                self.current_state_pending = True
                self.event_loop.call_later(0.5, self._process_state_change)
        elif state == 'OFF':
            pass  # not used in this alarm
        else:
            logger.warning('section %d in state %s', section, state)

    def _process_state_change(self):
        self.current_state_pending = False
        new_state = None
        for state in self.states.values():
            if state.matches(self.section_states):
                new_state = state.name
                break
        if new_state is None:
            logger.warning('uncoregnized alarm sections state: %s', self.section_states)
        elif new_state != self.current_state:
            self.current_state = new_state
            logger.info('alarm state changed to: %s', new_state)
            if self.homekit:
                self.homekit.update(new_state)

    @response_handler(r'(INTERNAL_WARNING|EXTERNAL_WARNING|FIRE_ALARM|INTRUDER_ALARM|PANIC_ALARM|ENTRY|EXIT) ([0-9]+) (ON|OFF)')
    def on_section_flag(self, flag, section, state):
        state = True if state == 'ON' else False
        if flag.endswith('_ALARM'):
            # TODO: keep track of all alarmed sections
            if state:
                self.current_state = STATE_TRIGGERED
                if self.homekit:
                    self.homekit.update(self.current_state)
            else:
                self._process_state_change()

    @response_handler(r'PRFSTATE ([0-9A-Z]+)')
    def on_prfstate(self, hex_state):
        state = binascii.unhexlify(hex_state)
        currently_active = set()
        for i in range(0, len(state)):
            for j in range(0, 8):
                if state[i] & (1 << j):
                    sid = i * 8 + j
                    if sid in self.sensors:
                        currently_active.add(self.sensors[sid])

        with self.update_lock:
            old_active = self.active_sensors
            self.active_sensors = currently_active

        for sensor in old_active - currently_active:
            logger.info('sensor deactivated: %s', sensor)
            sensor.value = False
        for sensor in currently_active - old_active:
            logger.info('sensor activated: %s', sensor)
            sensor.value = True

    def connection_lost(self, exc):
        logger.error('RS-485 connection lost')


async def create_connection(loop, config_file):
    def factory():
        return JablotronRS485(loop, config_file)
    _, protocol = await serial_asyncio.create_serial_connection(loop, factory, '/dev/ttyUSB0', baudrate=9600)
    await protocol.initialized_event.wait()
    logger.info('JablotronRS485 protocol initiated')
    return protocol
