<p align="center">
  <img src="https://raw.githubusercontent.com/kootenpv/sysdm/master/logo.png" width="300px"/>
</p>

[![PyPI](https://img.shields.io/pypi/v/sysdm.svg?style=flat-square)](https://pypi.python.org/pypi/sysdm/)
[![PyPI](https://img.shields.io/pypi/pyversions/sysdm.svg?style=flat-square)](https://pypi.python.org/pypi/sysdm/)

# sysdm

Scripts as a service. Builds on systemd.

It gives you the best from screen, cronjobs, supervisord, systemctl and journalctl.

### Installation

    pip install sysdm

### Demo

<p align="center">
  <img src="https://raw.githubusercontent.com/kootenpv/sysdm/master/demo.gif"/>
</p>

### Usage examples

    sysdm create myfile.py               # creates, starts and enables a new service file
    sysdm create exefile                 # executable/shell scripts are also supported
    sysdm create myfile.py --timer daily # the above + schedules it to run daily
    sysdm ls                             # see the known services created by sysdm
    sysdm delete                         # see the known services and select to delete
    sysdm run                            # run the app in the foreground (e.g for debugging)

    sysdm -h                             # general help
    sysdm <subcommand> -h                # help on subcommands
    

### Features

Creating and viewing have just helped you with:

- Generate a systemd unit file on the fly
- Uses current info to determine, and pin, working directory and virtualenv paths in your unit.
- Script will start running, and also boot on start
- Script will restart on error
- Script can also be started on a schedule (e.g. `--timer daily`), using systemd timers
- Changes to files in the directory of the same extension will cause a reload (e.g. `.py`)
- Provides a UI for inspecting the logs of your script and start, stop etc
- Like with screen, you can leave and it will keep on running.
- Multiple people can look at it, too, when sharing a server.
- Provides flags to change settings
- UI is aware of the window-size

### Public API

You can also embed `sysdm` in your code

It comes with this simple API that tells your all the units created by sysdm

```.python
def list_unit_info(systempath=None):
    """
    get a list of created sysdm units and their status

    :param systempath: Optional[str]. Folder where the service files are saved. It defaults to "~/.config/systemd/user"
        without sudo and otherwise to /etc/systemd/system.

    :return: Dict[str, Tuple[bool, bool, str] ]  a dict in the form of {unit_name:  (running, enabled, port)}.
        port can be an empty string
    """
```

```.python
from sysdm import list_unit_info

>>> list_unit_info()
{'service_0': (True, True, ''), 'service_1': (True, False, '')}
```