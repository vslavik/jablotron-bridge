
# Jablotron HomeKit Bridge

This is a bridge interfacing Jablotron alarms to HomeKit. It doesn't use Jablotron's online services that are high-latency and limited in functionality, but connects to the alarm system locally. It exposes:

- Alarm device itself
- Sensors (motion, contact) as HomeKit sensors
- Pseudo-buttons for manipulating alarm state without user confirmation

## Requirements

- JA-121T interface module for Jablotron alarms
- Linux-compatible USB-to-RS485 converter, e.g. based on FTDI/FT232RL (e.g. [Digitus](https://www.amazon.de/dp/B007VZY4CW/ref=pe_3044161_185740101_TE_item))
- A computer to run the service on (e.g. Raspberry Pi)

## Installation

The bridge uses Python 3 and Pipenv for dependencies. To install, cd into the source tree and do `pipenv install`.

### Configuration

1. Export list of sensors from the J-Link configuration software as XML file, e.g. into `jlink.xml`.
2. Run `pipenv run ./jlink2sensors.py jlink.xml >jablotron.toml`
3. Combine the resulting file with `jablotron.example.toml`
4. Edit the created configuration file as appropriate to assign human-meaningful names to sensors or to comment-out unwanted sensors.
5. Create a new user for HomeKit in J-Link and modify the `pin` setting in config accordingly. This is needed to change states; read only access doesn't require a PIN.


### Run

Run the service with `pipenv run ./jablotron_server.py`. See `jablotron.example.service` for an example systemd service.
