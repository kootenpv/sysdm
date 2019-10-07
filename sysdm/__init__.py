import os
import sys

from sysdm.sysctl import get_created_unit_names
from sysdm.utils import get_default_systempath, get_unit_info_by_names

__project__ = "sysdm"
__version__ = "0.7.30"
__repo__ = "https://github.com/kootenpv/sysdm"


def version():
    """ Prints the current version of rebrand, and more """
    sv = sys.version_info
    py_version = "{}.{}.{}".format(sv.major, sv.minor, sv.micro)
    version_parts = __version__.split(".")
    s = "{} version: [{}], Python {}".format(__project__, __version__, py_version)
    s += "\nMajor version: {}  (breaking changes)".format(version_parts[0])
    s += "\nMinor version: {}  (extra feature)".format(version_parts[1])
    s += "\nMicro version: {} (commit count)".format(version_parts[2])
    s += "\nFind out the most recent version at {}".format(__repo__)
    return s


def list_unit_info(systempath=None):
    """
    get a list of created sysdm units and their status

    :param systempath: Optional[str]. Folder where the service files are saved. It defaults to "~/.config/systemd/user"
        without sudo and otherwise to /etc/systemd/system.

    :return: Dict[str, Tuple[bool, bool, str] ]  a dict in the form of {unit_name:  (running, enabled, port)}.
        port can be an empty string
    """
    if systempath is None:
        systempath = get_default_systempath()
    systempath = os.path.expanduser(systempath)
    systempath = systempath.rstrip("/")

    unit_names = get_created_unit_names(systempath)
    return get_unit_info_by_names(unit_names, systempath)
