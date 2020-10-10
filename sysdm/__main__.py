import sys
import os
from pick import Picker
from sysdm.sysctl import (
    show,
    ls,
    delete,
    create_service_template,
    create_mail_on_failure_service,
    create_timer_service,
    create_service_monitor_template,
    linger,
)
from sysdm.file_watcher import watch
from sysdm.utils import (
    get_output,
    is_unit_running,
    is_unit_enabled,
    to_sn,
    systemctl,
    IS_SUDO,
    read_ps_aux_by_unit,
    get_port_from_ps_and_ss,
)
from cliche import cli, main
from sysdm.runner import monitor


class Sysdm:
    def __init__(self, systempath: str = None):
        """
        :param systempath: If None, gets expanded to "~/.config/systemd/user" without sudo
                           and otherwise to /etc/systemd/system.
        """
        if systempath is None:
            systempath = "/etc/systemd/system" if IS_SUDO else "~/.config/systemd/user"
        systempath = os.path.expanduser(systempath)
        systempath = systempath.rstrip("/")
        try:
            os.makedirs(systempath)
        except FileExistsError:
            pass
        self.systempath = systempath

    @cli
    def create(
        self,
        fname_or_cmd: str,
        restart=True,
        timer: str = None,
        killaftertimeout=90,
        delay=0.2,
        extensions=[],
        exclude_patterns=[],
        ls=True,
        root=False,
        notify_cmd="-1",
        notify_status_cmd="systemctl --user status -l -n 1000 %i",
        notify_cmd_args='-s "%i failed on %H"',
    ):
        """
        Create a systemd unit file

        :param fname_or_cmd: File/cmd to run
        :param restart: Whether to prevent auto restart on error
        :param timer: Used to set timer. Checked to be valid. E.g. *-*-* 03:00:00 for daily at 3 am.
        :param killaftertimeout: Time before sending kill signal if unresponsive when try to restart
        :param delay: Set a delay in the unit file before attempting restart
        :param extensions: Patterns of files to watch (by default inferred)
        :param exclude_patterns: Patterns of files to ignore (by default inferred)
        :param ls: Only create but do not list
        :param root: Only possible when using sudo
        :param notify_cmd: Binary command that will notify. -1 will add no notifier. Possible: e.g. yagmail
        :param notify_status_cmd: Command that echoes output to the notifier on failure
        :param notify_cmd_args: Arguments passed to notify command.
        """
        print("Creating systemd unit...")
        service_name, service = create_service_template(
            fname_or_cmd, notify_cmd, timer, delay, root, killaftertimeout
        )
        try:
            with open(os.path.join(self.systempath, service_name) + ".service", "w") as f:
                print(service)
                f.write(service)
        except PermissionError:
            print("Need sudo to create systemd unit service file.")
            sys.exit(1)
        create_mail_on_failure_service(
            self.systempath, notify_cmd, notify_status_cmd, notify_status_cmd, root
        )
        _ = systemctl("daemon-reload")
        create_timer = create_timer_service(self.systempath, service_name, timer)
        if create_timer:
            _ = systemctl("enable {}.timer".format(service_name))
            _ = systemctl("start {}.timer".format(service_name))
        else:
            _ = systemctl("enable {}".format(service_name))
            monitor_str = create_service_monitor_template(
                service_name, fname_or_cmd, extensions, exclude_patterns, root
            )
            with open(os.path.join(self.systempath, service_name) + "_monitor.service", "w") as f:
                f.write(monitor_str)
            _ = systemctl("start --no-block {}".format(service_name))
            _ = systemctl("enable {}_monitor".format(service_name))
            _ = systemctl("start {}_monitor".format(service_name))
        print(linger())
        print("Done")
        if ls:
            monitor(service_name, self.systempath)

    @cli
    def view(self, unit: str):
        """
        Monitor a unit

        :param unit: File/cmd/unit to observe. Dots will be replaced with _ automatically
        """
        service_name = to_sn(unit)
        if not os.path.exists(self.systempath + "/" + service_name + ".service"):
            print(
                "Service file does not exist. You can start by running:\n\n    sysdm create {}\n\nto create a service or run:\n\n    sysdm ls\n\nto see the services already created by sysdm.".format(
                    unit
                )
            )
            sys.exit(1)
        monitor(service_name, self.systempath)

    @cli
    def show_unit(self, unit: str = None):
        """
        Print out the definition of unit files for a unit

        :param unit: File/cmd/unit to print unit file. Dots will be replaced with _ automatically
        """
        if unit is None:
            units = ls(self.systempath)
            unit = choose_unit(self.systempath, units)
            if unit is None:
                sys.exit()
        show(self.systempath, unit)

    @cli
    def ls(self):
        """ Interactively show units and allow viewing them """
        while True:
            units = ls(self.systempath)
            if units:
                unit = choose_unit(self.systempath, units)
                if unit is None:
                    sys.exit()
                monitor(unit, self.systempath)
            else:
                print(
                    "sysdm knows of no units. Why don't you make one? `sysdm create file_i_want_as_service.py`"
                )
                break

    @cli
    def edit(self, unit: str = None):
        """
        Opens a unit service file for editing

        :param unit: File/cmd/unit to edit. When omitted, show choices.
        """
        if unit is None:
            units = ls(self.systempath)
            unit = choose_unit(self.systempath, units)
            if unit is None:
                sys.exit()
        unit = unit if unit.endswith(".service") else unit + ".service"
        os.system("$EDITOR {}/{}".format(self.systempath, unit))

    @cli
    def run(self, unit: str = None, debug=False):
        """
        Run the command of a unit once

        :param unit: File/cmd/unit to run.
        :param debug: Use debug on error if available
        """
        if unit is None:
            units = ls(self.systempath)
            unit = choose_unit(self.systempath, units)
            if unit is None:
                sys.exit()
        with open(self.systempath + "/" + unit + ".service") as f:
            for line in f:
                line = line.strip()
                if line.startswith("ExecStart="):
                    cmd = line.split("ExecStart=")[1]
                    if debug:
                        cmd = cmd.replace("python3 -u", "python3 -u -m pdb")
                        cmd = cmd.replace("python -u", "python -u -m pdb")
                elif line.startswith("WorkingDirectory="):
                    cwd = line.split("WorkingDirectory=")[1]
            os.system("cd {!r} && {}".format(cwd, cmd))

    @cli
    def delete(self, unit: str = None):
        """
        Delete a unit

        :param unit: File/cmd/unit to delete. When omitted, show choices.
        """
        if unit is None:
            units = ls(self.systempath)
            unit = choose_unit(self.systempath, units)
            if unit is None:
                sys.exit()
            inp = input("Are you sure you want to delete '{}'? [y/N]: ".format(unit))
            if inp.lower().strip() != "y":
                print("Aborting")
                return
        delete(unit, self.systempath)


@cli
def file_watch(extensions=[], exclude_patterns=[]):
    """
    Internal use.

    :param extensions: Patterns of files to watch (by default inferred)
    :param exclude_patterns: Patterns of files to ignore (by default inferred)
    """
    watch(extensions, exclude_patterns)


@cli
def reload():
    """
    Do a daemon-reload for systemd
    """
    systemctl("daemon-reload")


def choose_unit(systempath, units):
    options = []
    ss = get_output("ss -l -p -n")
    ps_aux = get_output("ps ax -o pid,%cpu,%mem,ppid,args -ww")
    for unit in units:
        running = "✓" if is_unit_running(unit) or is_unit_running(unit + ".timer") else "✗"
        enabled = "✓" if is_unit_enabled(unit) or is_unit_enabled(unit + ".timer") else "✗"
        ps = read_ps_aux_by_unit(systempath, unit, ps_aux)
        if ps is None:
            port = ""
        else:
            pid, *_ = ps
            port = get_port_from_ps_and_ss(pid, ss)
        options.append((unit, running, enabled, port))

    pad = "{}|    {}    |    {}    |   {}"
    offset = max([len(x[0]) for x in options]) + 3
    formatted_options = [pad.format(x.ljust(offset), r, e, p) for x, r, e, p in options]
    quit = "-- Quit --"
    formatted_options.append(" ")
    formatted_options.append(quit)
    title = "These are known units:\n\n{}| Active  | On boot |   Port".format(" " * (offset + 2))
    default_index = 0
    while True:
        p = Picker(formatted_options, title, default_index=default_index)
        p.register_custom_handler(ord('q'), lambda _: sys.exit(0))
        chosen, index = p.start()
        if chosen == quit:
            return None
        elif chosen == " ":
            default_index = index
            continue
        else:
            break
    return units[index]


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Aborted")
