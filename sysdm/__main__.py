import sys
import os
from pick import Picker
from sysdm.sysctl import (
    show,
    ls,
    delete,
    create_service_template,
    create_notification_on_failure_service,
    create_timer_service,
    create_service_monitor_template,
    linger,
    reload,
    stop_and_disable,
    print_status_table,
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
from sysdm.notify import notify, install_notifier_dependencies
from typing import Optional, Union
import json as json_module


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
        timer: list[str] = None,
        killaftertimeout=90,
        delay=0.2,
        extensions=[],
        exclude_patterns=[],
        ls=True,
        root=False,
        n_notifier: Optional[str] = None,
        n_user: Optional[str] = None,
        n_to: Optional[Union[str, int]] = None,
        n_pw: Optional[str] = None,
        n_msg: Optional[str] = "%i failed on %H",
        n_status_cmd="journalctl {user} --no-pager -n 1000",
        workdir: str = "",
        env_vars: list[str] = [],
    ):
        """Create a systemd unit file

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
        :param workdir: Location from which command is run
        :param env_vars: can be passed like FOO=1 or FOO (which would inherit FOO current shell)
        """
        if n_notifier is not None:
            install_notifier_dependencies(n_notifier)
        print("Creating systemd unit...")
        service_name, service = create_service_template(
            fname_or_cmd, n_notifier, timer, delay, root, killaftertimeout, restart, workdir, env_vars
        )
        user = "-u %i" if IS_SUDO else "--user-unit %i"
        n_status_cmd = n_status_cmd.format(user=user)
        try:
            with open(os.path.join(self.systempath, service_name) + ".service", "w") as f:
                print(service)
                f.write(service)
        except PermissionError:
            print("Need sudo to create systemd unit service file.")
            sys.exit(1)
        create_notification_on_failure_service(
            self.systempath, service_name, n_notifier, n_user, n_to, n_pw, n_msg, n_status_cmd, root
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
        """Monitor a unit [interactive]

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
        """Show the unit file contents [interactive]

        :param unit: File/cmd/unit to print unit file. Dots will be replaced with _ automatically
        """
        if unit is None:
            units = ls(self.systempath)
            unit = choose_unit(self.systempath, units)
            if unit is None:
                sys.exit()
        show(self.systempath, unit)

    @cli
    def stop_all(self):
        """Stop all running sysdm-managed units"""
        units = ls(self.systempath)
        for unit in units:
            if is_unit_running(unit):
                print("Stopping unit", unit)
                systemctl("stop {}".format(unit))

    @cli
    def ls(self, json: bool = False):
        """List and manage sysdm-managed units [interactive]

        :param json: Output unit data as JSON instead of interactive mode
        """
        units = ls(self.systempath)
        if json:
            data = get_units_data(self.systempath, units)
            print(json_module.dumps(data, indent=2))
            return
        while True:
            if units:
                unit = choose_unit(self.systempath, units)
                if unit is None:
                    sys.exit()
                while True:
                    action = monitor(unit, self.systempath)
                    if action == "edit":
                        self.edit(unit)
                    elif not action:
                        break
            else:
                print("sysdm knows of no units. Why don't you make one? `sysdm create file_i_want_as_service.py`")
                break

    @cli
    def export(self, unit: str = None):
        """Export sysdm-managed unit files as JSON

        :param unit: File/cmd/unit to export. When omitted, exports all units.
        """
        units = ls(self.systempath)
        if not units:
            print("No sysdm-managed units found.", file=sys.stderr)
            return
        if unit is not None:
            service_name = to_sn(unit)
            if service_name not in units:
                print("Unit '{}' not found. Available units:".format(unit), file=sys.stderr)
                for u in units:
                    print("  - {}".format(u), file=sys.stderr)
                sys.exit(1)
            units = [service_name]
        data = []
        for unit_name in units:
            entry = {"unit": unit_name, "files": {}}
            suffixes = [".service", "_monitor.service", ".timer"]
            for suffix in suffixes:
                fpath = os.path.join(self.systempath, unit_name + suffix)
                if os.path.exists(fpath):
                    with open(fpath) as f:
                        entry["files"][suffix] = f.read()
            data.append(entry)
        print(json_module.dumps(data, indent=2))

    @cli
    def import_units(self, fpath: str, unit: str = None):
        """Import sysdm unit files from a JSON export

        :param fpath: Path to the JSON file (or - for stdin)
        :param unit: Only import this specific unit from the export
        """
        if fpath == "-":
            data = json_module.load(sys.stdin)
        else:
            with open(fpath) as f:
                data = json_module.load(f)
        if unit is not None:
            service_name = to_sn(unit)
            data = [e for e in data if e["unit"] == service_name]
            if not data:
                print("Unit '{}' not found in export.".format(unit), file=sys.stderr)
                sys.exit(1)
        before = {}
        for entry in data:
            unit_name = entry["unit"]
            for s in [unit_name, unit_name + "_monitor", unit_name + ".timer"]:
                before[s] = (is_unit_enabled(s), is_unit_running(s))
            stop_and_disable(unit_name)
            for suffix, content in entry["files"].items():
                dest = os.path.join(self.systempath, unit_name + suffix)
                with open(dest, "w") as f:
                    f.write(content)
                print("Wrote {}".format(dest))
        systemctl("daemon-reload")
        for entry in data:
            unit_name = entry["unit"]
            if ".timer" in entry["files"]:
                systemctl("enable {}.timer".format(unit_name))
                systemctl("start {}.timer".format(unit_name))
            else:
                systemctl("enable {}".format(unit_name))
                systemctl("start --no-block {}".format(unit_name))
                if "_monitor.service" in entry["files"]:
                    systemctl("enable {}_monitor".format(unit_name))
                    systemctl("start {}_monitor".format(unit_name))
        rows = []
        for entry in data:
            unit_name = entry["unit"]
            suffixes = {".service": "", "_monitor.service": "_monitor", ".timer": ".timer"}
            for suffix, sub in suffixes.items():
                if suffix in entry["files"] or before.get(unit_name + sub, (False, False)) != (False, False):
                    s = unit_name + sub
                    be, ba = before[s]
                    ae = is_unit_enabled(s)
                    aa = is_unit_running(s)
                    rows.append((s, be, ba, ae, aa))
        print_status_table(rows)
        print("Imported {} unit(s).".format(len(data)))

    @cli
    def edit(self, unit: str = None):
        """Edit a unit service file [interactive]

        :param unit: File/cmd/unit to edit. When omitted, show choices.
        """
        if unit is None:
            units = ls(self.systempath)
            unit = choose_unit(self.systempath, units)
            if unit is None:
                sys.exit()
        unit = unit if unit.endswith(".service") else unit + ".service"
        os.system("${{EDITOR=vim}} {}/{}".format(self.systempath, unit))

    @cli
    def run(self, unit: str = None, debug=False):
        """Run a unit's command once [interactive]

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
        """Delete a unit [interactive]

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
    """Internal: watches files for changes to trigger restarts

    :param extensions: Patterns of files to watch (by default inferred)
    :param exclude_patterns: Patterns of files to ignore (by default inferred)
    """
    watch(extensions, exclude_patterns)


def get_units_data(systempath, units):
    """Get unit data as a list of dictionaries."""
    ss = get_output("ss -l -p -n 2>/dev/null")
    ps_aux = get_output("ps ax -o pid,%cpu,%mem,ppid,args -ww")
    data = []
    for unit in units:
        running = is_unit_running(unit) or is_unit_running(unit + ".timer")
        enabled = is_unit_enabled(unit) or is_unit_enabled(unit + ".timer")
        ps = read_ps_aux_by_unit(systempath, unit, ps_aux)
        port = None
        if ps is not None:
            pid, *_ = ps
            port = get_port_from_ps_and_ss(pid, ss) or None
        data.append({
            "unit": unit,
            "active": running,
            "enabled": enabled,
            "port": port,
        })
    return data


def choose_unit(systempath, units):
    options = []
    ss = get_output("ss -l -p -n 2>/dev/null")
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

    options.sort(key=lambda x: (x[1] != "✓", x[2] != "✓", x[0]))

    offset = max([len(x[0]) for x in options]) + 2
    port_width = max((len(p) for _, _, _, p in options if p), default=4)
    port_width = max(port_width, 4)
    # picker adds 2-char prefix ("* " or "  "), so header needs 2 extra chars
    header = "  {} │ Active │ On boot │ {}".format("Unit".ljust(offset), "Port".ljust(port_width))
    sep = "──{}─┼────────┼─────────┼─{}".format("─" * offset, "─" * (port_width + 1))
    header_row = "{} │ Active │ On boot │ {}".format("Unit".ljust(offset), "Port".ljust(port_width))
    sep_row = "{}─┼────────┼─────────┼─{}".format("─" * offset, "─" * (port_width + 1))
    formatted_options = [header_row, sep_row]
    for x, r, e, p in options:
        formatted_options.append(
            "{} │   {}    │    {}    │ {}".format(x.ljust(offset), r, e, p.ljust(port_width))
        )
    quit = "-- Quit --"
    formatted_options.append(" ")
    formatted_options.append(quit)
    title = "These are known units:"
    # first 2 rows are header/separator, start selection on first real unit
    default_index = 2
    while True:
        p = Picker(formatted_options, title, default_index=default_index, quit_keys=[ord("q")])
        chosen, index = p.start()
        if chosen is None or chosen == quit:
            return None
        elif chosen in (" ", header_row, sep_row):
            default_index = index
            continue
        else:
            break
    return options[index - 2][0]


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Aborted")
