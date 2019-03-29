<p align="center">
  <img src="https://raw.githubusercontent.com/kootenpv/sysdm/master/logo.png" width="300px"/>
</p>

[![PyPI](https://img.shields.io/pypi/v/sysdm.svg?style=flat-square)](https://pypi.python.org/pypi/sysdm/)
[![PyPI](https://img.shields.io/pypi/pyversions/sysdm.svg?style=flat-square)](https://pypi.python.org/pypi/sysdm/)

# sysdm

Scripts as a service. Builds on systemd.

It gives you the best from screen, systemctl and journalctl.

### Installation

    pip install sysdm

### Usage

    sudo sysdm create myfile.py # creates and enables a new service file
    sysdm view myfile.py        # tails the service logs and allows interaction

### Features

Creating and viewing have just helped you with:

- Generate a systemd unit file on the fly
- Uses current info to determine, and pin, working directory and virtualenv paths in your unit.
- Script will start running, and also boot on start
- Script will restart on error
- Changes to files in the directory of the same extension will cause a reload
- Provides a UI for inspecting the logs of your script and start, stop etc
- Like with screen, you can leave and it will keep on running.
- Multiple people can look at it, too, when sharing a server.
- Provides flags to change settings
- UI is aware of the window-size

### Screenshot

<p align="center">
  <img src="https://raw.githubusercontent.com/kootenpv/sysdm/master/screenshot.png"/>
</p>
