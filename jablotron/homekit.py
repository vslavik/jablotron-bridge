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
import weakref

from pyhap.accessory import Bridge
from pyhap.accessory_driver import AccessoryDriver
from pyhap.accessory import Accessory
from pyhap.const import CATEGORY_ALARM_SYSTEM, CATEGORY_SENSOR

from .core import Sensor, STATE_DISARMED, STATE_AWAY, STATE_HOME, STATE_NIGHT, STATE_TRIGGERED

_core_to_homekit = {
    STATE_HOME: 0,
    STATE_AWAY: 1,
    STATE_NIGHT: 2,
    STATE_DISARMED: 3,
    STATE_TRIGGERED: 4,
}
_homekit_to_core = {c: s for s, c in _core_to_homekit.items()}


logger = logging.getLogger(__name__)


class HKSensor(Accessory):

    category = CATEGORY_SENSOR

    def __init__(self, driver, sensor):
        super().__init__(driver, sensor.name)
        self.char = None
        self.sensor = sensor
        sensor.homekit = weakref.proxy(self)
        char = driver.loader.get_char('FirmwareRevision')
        self.get_service('AccessoryInformation').add_characteristic(char)
        self.set_info_service(model=sensor.model,
                              manufacturer='Jablotron',
                              serial_number='{} | #{}'.format(sensor.alarm.serial_number, sensor.id),
                              firmware_revision=sensor.alarm.firmware_version)

    def update(self, value):
        self.char.set_value(value)


class MotionSensor(HKSensor):
    def __init__(self, driver, sensor):
        super().__init__(driver, sensor)
        service = self.add_preload_service('MotionSensor')
        self.char = service.configure_char('MotionDetected')


class ContactSensor(HKSensor):
    def __init__(self, driver, sensor):
        super().__init__(driver, sensor)
        service = self.add_preload_service('ContactSensor')
        self.char = service.configure_char('ContactSensorState')


def create_sensor_accessory(driver, sensor):
    if sensor.kind == Sensor.MOTION:
        return MotionSensor(driver, sensor)
    elif sensor.kind == Sensor.WINDOW:
        return ContactSensor(driver, sensor)
    else:
        return ContactSensor(driver, sensor)


class Alarm(Accessory):
    category = CATEGORY_ALARM_SYSTEM

    def __init__(self, driver, core_alarm, config, aid=None):
        super().__init__(driver, 'Alarm', aid)
        self.alarm = core_alarm
        serv_alarm = self.add_preload_service('SecuritySystem')
        current_state = _core_to_homekit.get(core_alarm.current_state, 3)
        self.char_current_state = serv_alarm.configure_char('SecuritySystemCurrentState', value=current_state)
        self.char_target_state = serv_alarm.configure_char('SecuritySystemTargetState', value=current_state,
                                                           setter_callback=self.set_hk_alarm_state)
        self.toggles = {}
        for s in config.get('fake_buttons', []):
            serv_button = self.add_preload_service('Switch', chars=['Name'])
            serv_button.configure_char('Name', value='Alarm→{}'.format(s))
            self.toggles[s] = serv_button.configure_char('On', setter_callback=lambda x, s=s: self.toggle_fake_button(s, x))

        core_alarm.homekit = weakref.proxy(self)

    def update(self, value):
        state = _core_to_homekit.get(value, 1)
        logger.info('setting homekit security state to %d from "%s"', state, value)
        self.char_current_state.set_value(state)
        if value != STATE_TRIGGERED:
            self.char_target_state.set_value(state)
        for name, button in self.toggles.items():
            button.set_value(name == value)

    def set_alarm_state(self, state):
        """Move security state to value if call came from HomeKit."""
        logger.info('setting security state to %s ', state)
        hk_state = _core_to_homekit.get(state, None)
        if hk_state is not None:
            self.char_target_state.set_value(hk_state)
        self.alarm.set_alarm_state(state)

    def set_hk_alarm_state(self, state):
        self.set_alarm_state(_homekit_to_core[state])

    def toggle_fake_button(self, button, on):
        if on:
            self.set_alarm_state(button)


def create_driver(loop, core_alarm):
    config = core_alarm.config.get('homekit', {})
    use_bridge = core_alarm.sensors or config.get('use_bridge', False)

    driver = AccessoryDriver(loop=loop, port=config.get('port', 51001))
    alarm = Alarm(driver, core_alarm, config)
    alarm.set_info_service(model=core_alarm.model,
                          manufacturer='Jablotron',
                          serial_number=core_alarm.serial_number,
                          firmware_revision=core_alarm.firmware_version)

    if use_bridge:
        bridge = Bridge(driver, display_name='Jablotron Bridge')
        bridge.set_info_service(model=core_alarm.model,
                                manufacturer='Jablotron',
                                serial_number=core_alarm.serial_number,
                                firmware_revision=core_alarm.firmware_version)
        bridge.add_accessory(alarm)
        for s in core_alarm.sensors.values():
            bridge.add_accessory(create_sensor_accessory(driver, s))
        driver.add_accessory(bridge)
    else:
        driver.add_accessory(alarm)

    return driver
