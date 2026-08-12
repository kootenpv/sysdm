import sys
import os
import shutil
from sysdm.sysctl import (
    show,
    ls as _ls,
    delete as _delete,
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
    read_command_from_unit,
    get_port_from_ps_and_ss,
    batch_systemctl_show,
)
from cliche import cli
from sysdm.runner import monitor
from sysdm.notify import notify, install_notifier_dependencies
from typing import Optional, Union
import json as json_module


def _get_systempath(systempath: str = None) -> str:
    if systempath is None:
        systempath = "/etc/systemd/system" if IS_SUDO else "~/.config/systemd/user"
    systempath = os.path.expanduser(systempath)
    systempath = systempath.rstrip("/")
    os.makedirs(systempath, exist_ok=True)
    return systempath


@cli
def create(
    fname_or_cmd: str,
    restart: bool = True,
    timer: list[str] = None,
    killaftertimeout=90,
    delay=0.2,
    extensions=[],
    exclude_patterns=[],
    ls_after: bool = True,
    root: bool = False,
    n_notifier: Optional[str] = None,
    n_user: Optional[str] = None,
    n_to: Optional[Union[str, int]] = None,
    n_pw: Optional[str] = None,
    n_msg: Optional[str] = "%i failed on %H",
    n_status_cmd="journalctl {user} --no-pager -n 1000",
    workdir: str = "",
    env_vars: list[str] = [],
    systempath: str = None,
    unit_name: str = "",
):
    """Create a systemd unit file

    :param fname_or_cmd: File/cmd to run
    :param restart: Whether to prevent auto restart on error
    :param timer: Used to set timer. Checked to be valid. E.g. *-*-* 03:00:00 for daily at 3 am.
    :param killaftertimeout: Time before sending kill signal if unresponsive when try to restart
    :param delay: Set a delay in the unit file before attempting restart
    :param extensions: Patterns of files to watch (by default inferred)
    :param exclude_patterns: Patterns of files to ignore (by default inferred)
    :param ls_after: Only create but do not list
    :param root: Only possible when using sudo
    :param n_notifier: Notifier to use (e.g. telegram, yagmail, notify-send)
    :param n_status_cmd: Command that echoes output to the notifier on failure
    :param workdir: Location from which command is run
    :param env_vars: can be passed like FOO=1 or FOO (which would inherit FOO current shell)
    :param systempath: Path to systemd directory
    :param unit_name: Force a specific unit name (used for both the service and its monitor). Empty = auto-derive.
    """
    systempath = _get_systempath(systempath)
    if n_notifier is not None:
        install_notifier_dependencies(n_notifier)
    print("Creating systemd unit...")
    service_name, service = create_service_template(
        fname_or_cmd, n_notifier, timer, delay, root, killaftertimeout, restart, workdir, env_vars,
        unit_name=unit_name,
    )
    user = "-u %i" if IS_SUDO else "--user-unit %i"
    n_status_cmd = n_status_cmd.format(user=user)
    try:
        with open(os.path.join(systempath, service_name) + ".service", "w") as f:
            print(service)
            f.write(service)
    except PermissionError:
        print("Need sudo to create systemd unit service file.")
        sys.exit(1)
    create_notification_on_failure_service(
        systempath, service_name, n_notifier, n_user, n_to, n_pw, n_msg, n_status_cmd, root
    )
    _ = systemctl("daemon-reload")
    create_timer = create_timer_service(systempath, service_name, timer)
    if create_timer:
        _ = systemctl("enable {}.timer".format(service_name))
        _ = systemctl("start {}.timer".format(service_name))
    else:
        _ = systemctl("enable {}".format(service_name))
        monitor_str = create_service_monitor_template(
            service_name, fname_or_cmd, extensions, exclude_patterns, root
        )
        with open(os.path.join(systempath, service_name) + "_monitor.service", "w") as f:
            f.write(monitor_str)
        _ = systemctl("start --no-block {}".format(service_name))
        _ = systemctl("enable {}_monitor".format(service_name))
        _ = systemctl("start {}_monitor".format(service_name))
    print(linger())
    print("Done")
    if ls_after:
        monitor(service_name, systempath)


@cli
def view(unit: str, systempath: str = None):
    """Monitor a unit [interactive]

    :param unit: File/cmd/unit to observe. Dots will be replaced with _ automatically
    :param systempath: Path to systemd directory
    """
    systempath = _get_systempath(systempath)
    service_name = to_sn(unit)
    if not os.path.exists(systempath + "/" + service_name + ".service"):
        print(
            "Service file does not exist. You can start by running:\n\n    sysdm create {}\n\nto create a service or run:\n\n    sysdm ls\n\nto see the services already created by sysdm.".format(
                unit
            )
        )
        sys.exit(1)
    monitor(service_name, systempath)


@cli
def show_unit(unit: str = None, systempath: str = None):
    """Show the unit file contents [interactive]

    :param unit: File/cmd/unit to print unit file. Dots will be replaced with _ automatically
    :param systempath: Path to systemd directory
    """
    systempath = _get_systempath(systempath)
    if unit is None:
        units = _ls(systempath)
        unit = choose_unit(systempath, units)
        if unit is None:
            sys.exit()
    show(systempath, unit)


@cli
def stop_all(systempath: str = None):
    """Stop all running sysdm-managed units

    :param systempath: Path to systemd directory
    """
    systempath = _get_systempath(systempath)
    units = _ls(systempath)
    for unit in units:
        if is_unit_running(unit):
            print("Stopping unit", unit)
            systemctl("stop {}".format(unit))


@cli
def ls(json: bool = False, systempath: str = None):
    """List and manage sysdm-managed units [interactive]

    :param json: Output unit data as JSON instead of interactive mode
    :param systempath: Path to systemd directory
    """
    systempath = _get_systempath(systempath)
    units = _ls(systempath)
    if json:
        data = get_units_data(systempath, units)
        print(json_module.dumps(data, indent=2))
        return
    while True:
        if units:
            unit = choose_unit(systempath, units)
            if unit is None:
                sys.exit()
            while True:
                action = monitor(unit, systempath)
                if action == "edit":
                    edit(unit, systempath)
                elif not action:
                    break
        else:
            print("sysdm knows of no units. Why don't you make one? `sysdm create file_i_want_as_service.py`")
            break


@cli
def export(unit: str = None, systempath: str = None):
    """Export sysdm-managed unit files as JSON

    :param unit: File/cmd/unit to export. When omitted, exports all units.
    :param systempath: Path to systemd directory
    """
    systempath = _get_systempath(systempath)
    units = _ls(systempath)
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
            fpath = os.path.join(systempath, unit_name + suffix)
            if os.path.exists(fpath):
                with open(fpath) as f:
                    entry["files"][suffix] = f.read()
        data.append(entry)
    print(json_module.dumps(data, indent=2))


@cli
def import_units(fpath: str, unit: str = None, systempath: str = None):
    """Import sysdm unit files from a JSON export

    :param fpath: Path to the JSON file (or - for stdin)
    :param unit: Only import this specific unit from the export
    :param systempath: Path to systemd directory
    """
    systempath = _get_systempath(systempath)
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
            dest = os.path.join(systempath, unit_name + suffix)
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
def edit(unit: str = None, systempath: str = None):
    """Edit a unit service file [interactive]

    :param unit: File/cmd/unit to edit. When omitted, show choices.
    :param systempath: Path to systemd directory
    """
    systempath = _get_systempath(systempath)
    if unit is None:
        units = _ls(systempath)
        unit = choose_unit(systempath, units)
        if unit is None:
            sys.exit()
    unit = unit if unit.endswith(".service") else unit + ".service"
    os.system("${{EDITOR=vim}} {}/{}".format(systempath, unit))


@cli
def run(unit: str = None, debug=False, systempath: str = None):
    """Run a unit's command once [interactive]

    :param unit: File/cmd/unit to run.
    :param debug: Use debug on error if available
    :param systempath: Path to systemd directory
    """
    systempath = _get_systempath(systempath)
    if unit is None:
        units = _ls(systempath)
        unit = choose_unit(systempath, units)
        if unit is None:
            sys.exit()
    with open(systempath + "/" + unit + ".service") as f:
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
def delete(unit: str = None, systempath: str = None):
    """Delete a unit [interactive]

    :param unit: File/cmd/unit to delete. When omitted, show choices.
    :param systempath: Path to systemd directory
    """
    systempath = _get_systempath(systempath)
    if unit is None:
        units = _ls(systempath)
        unit = choose_unit(systempath, units)
        if unit is None:
            sys.exit()
        inp = input("Are you sure you want to delete '{}'? [y/N]: ".format(unit))
        if inp.lower().strip() != "y":
            print("Aborting")
            return
    _delete(unit, systempath)


@cli
def file_watch(extensions=[], exclude_patterns=[]):
    """Internal: watches files for changes to trigger restarts

    :param extensions: Patterns of files to watch (by default inferred)
    :param exclude_patterns: Patterns of files to ignore (by default inferred)
    """
    watch(extensions, exclude_patterns)


def get_env_vars(systempath, unit):
    """Get environment variable names set in a unit file, excluding PYTHONUNBUFFERED."""
    try:
        with open(os.path.join(systempath, unit + ".service")) as f:
            lines = f.readlines()
        env_names = []
        for line in lines:
            line = line.strip()
            if line.startswith("Environment="):
                val = line[len("Environment="):]
                name = val.split("=", 1)[0]
                if name != "PYTHONUNBUFFERED":
                    env_names.append(name)
        return ", ".join(env_names)
    except (FileNotFoundError, Exception):
        return ""


def _strip_ansi(s):
    import re
    return re.sub(r'\x1b\[[0-9;]*m', '', s)


def get_last_log_line(unit):
    """Get the last informative log line for a unit, skipping systemd lifecycle messages."""
    u_sep = "-u" if IS_SUDO else "--user-unit"
    cmd = 'journalctl {u} {unit} {u} {unit}_monitor {u} {unit}.timer --no-pager -q -n 20 -o cat 2>/dev/null'.format(u=u_sep, unit=unit)
    try:
        lines = get_output(cmd).strip().split("\n")
        skip = ("Started ", "Stopped ", "Stopping ", "Starting ", "Failed to start ",
                "finished", "generated by sysdm", "Main process exited",
                "Consumed ", "Deactivated successfully", "Failed with result",
                "Scheduled restart job", "Start request repeated too quickly")
        for line in reversed(lines):
            line = _strip_ansi(line.strip())
            if line and not any(s in line for s in skip):
                return line
        return _strip_ansi(lines[-1].strip()) if lines and lines[-1].strip() else ""
    except Exception:
        return ""


# Counting exact journal volume is O(lines): a chatty unit (e.g. 600k lines/day)
# makes `journalctl | wc -l` take many seconds. We only need an activity signal,
# so cap with -n: journalctl emits at most LOG_24H_CAP recent lines and counting
# stops there. A count == cap is reported as "{cap}+".
LOG_24H_CAP = 2000


def get_log_lines_24h(unit):
    """Get the number of journal log lines in the last 24 hours for a unit, capped at LOG_24H_CAP."""
    u_sep = "-u" if IS_SUDO else "--user-unit"
    cmd = 'journalctl {} {} --since "24 hours ago" -n {} --no-pager -q 2>/dev/null | wc -l'.format(
        u_sep, unit, LOG_24H_CAP)
    try:
        count = get_output(cmd).strip()
        return int(count)
    except (ValueError, Exception):
        return 0


def gather_unit_info(systempath, units):
    """Single batched systemctl show call for all units + their .timer counterparts."""
    all_units = []
    for unit in units:
        all_units.append(unit)
        if os.path.exists(os.path.join(systempath, unit + ".timer")):
            all_units.append(unit + ".timer")
    props = ["ActiveState", "UnitFileState", "MainPID", "NRestarts",
             "ExecMainStatus", "NextElapseUSecRealtime"]
    return batch_systemctl_show(all_units, props)


def get_timer_schedule(units, info):
    """Build dict of unit -> next-run-time string from a pre-fetched info map."""
    timers = {}
    for unit in units:
        next_time = info.get(unit + ".timer", {}).get("NextElapseUSecRealtime", "").strip()
        if next_time and next_time != "n/a":
            parts2 = next_time.split()
            if len(parts2) >= 3:
                timers[unit] = parts2[1] + " " + parts2[2][:5]
    return timers


def get_units_data(systempath, units):
    """Get unit data as a list of dictionaries."""
    from concurrent.futures import ThreadPoolExecutor
    ss = get_output("ss -l -p -n 2>/dev/null")
    ps_aux = get_output("ps ax -o pid,%cpu,%mem,ppid,args -ww")
    info = gather_unit_info(systempath, units)
    timers = get_timer_schedule(units, info)
    if units:
        with ThreadPoolExecutor(max_workers=min(16, len(units))) as ex:
            log_lines_map = dict(zip(units, ex.map(get_log_lines_24h, units)))
            last_log_map = dict(zip(units, ex.map(get_last_log_line, units)))
    else:
        log_lines_map = {}
        last_log_map = {}
    data = []
    for unit in units:
        u_info = info.get(unit, {})
        t_info = info.get(unit + ".timer", {})
        running = u_info.get("ActiveState") == "active" or t_info.get("ActiveState") == "active"
        enabled = u_info.get("UnitFileState") == "enabled" or t_info.get("UnitFileState") == "enabled"
        main_pid = u_info.get("MainPID", "0")
        ps = read_ps_aux_by_unit(systempath, unit, ps_aux, main_pid=main_pid)
        port = None
        cpu = None
        mem = None
        if ps is not None:
            pid, cpu, mem = ps
            port = get_port_from_ps_and_ss(pid, ss, ps_aux) or None
        log_lines = log_lines_map.get(unit, 0)
        env_vars = get_env_vars(systempath, unit)
        try:
            restarts = int(u_info.get("NRestarts", "0") or 0)
        except ValueError:
            restarts = 0
        try:
            code = int(u_info.get("ExecMainStatus", "0") or 0)
            exit_status = code if code != 0 else None
        except ValueError:
            exit_status = None
        last_log = last_log_map.get(unit, "")
        next_run = timers.get(unit, "")
        data.append({
            "unit": unit,
            "active": running,
            "enabled": enabled,
            "port": port,
            "cpu": cpu,
            "mem": mem,
            "restarts": restarts,
            "exit": exit_status,
            "log_24h": log_lines,
            "env": env_vars,
            "last_log": last_log,
            "next_run": next_run,
        })
    return data


def choose_unit(systempath, units):
    from textual.app import App, ComposeResult
    from textual.widgets import DataTable, Static
    from textual.binding import Binding
    from rich.text import Text
    from concurrent.futures import ThreadPoolExecutor

    rows = []
    ss = get_output("ss -l -p -n 2>/dev/null")
    ps_aux = get_output("ps ax -o pid,%cpu,%mem,ppid,args -ww")
    info = gather_unit_info(systempath, units)
    timers = get_timer_schedule(units, info)
    # Parallelize the per-unit journalctl calls — they dominate ls runtime.
    if units:
        with ThreadPoolExecutor(max_workers=min(16, len(units))) as ex:
            log_lines_map = dict(zip(units, ex.map(get_log_lines_24h, units)))
            last_log_map = dict(zip(units, ex.map(get_last_log_line, units)))
    else:
        log_lines_map = {}
        last_log_map = {}
    for unit in units:
        u_info = info.get(unit, {})
        t_info = info.get(unit + ".timer", {})
        is_running = u_info.get("ActiveState") == "active" or t_info.get("ActiveState") == "active"
        is_enabled = u_info.get("UnitFileState") == "enabled" or t_info.get("UnitFileState") == "enabled"
        running = "[green]✓[/]" if is_running else "[red]✗[/]"
        enabled = "[green]✓[/]" if is_enabled else "[red]✗[/]"
        main_pid = u_info.get("MainPID", "0")
        ps = read_ps_aux_by_unit(systempath, unit, ps_aux, main_pid=main_pid)
        if ps is None:
            port = ""
            cpu = ""
            mem = ""
            pid_str = ""
        else:
            pid, cpu, mem = ps
            pid_str = pid
            port = get_port_from_ps_and_ss(pid, ss, ps_aux)
        log_lines = log_lines_map.get(unit, 0)
        try:
            restarts = int(u_info.get("NRestarts", "0") or 0)
        except ValueError:
            restarts = 0
        try:
            code = int(u_info.get("ExecMainStatus", "0") or 0)
            exit_status = code if code != 0 else None
        except ValueError:
            exit_status = None
        env_vars = get_env_vars(systempath, unit)
        last_log = last_log_map.get(unit, "")
        try:
            exec_cmd = read_command_from_unit(systempath, unit) or ""
        except Exception:
            exec_cmd = ""
        try:
            cwd = ""
            with open(os.path.join(systempath, unit + ".service")) as f:
                for line in f:
                    if line.strip().startswith("WorkingDirectory="):
                        cwd = line.strip()[len("WorkingDirectory="):]
                        break
            home = os.path.expanduser("~")
            if cwd.startswith(home):
                cwd = "~" + cwd[len(home):]
        except Exception:
            cwd = ""
        try:
            unit_path = os.path.join(systempath, unit + ".service")
            created_ts = os.path.getmtime(unit_path)
            from datetime import datetime
            created = datetime.fromtimestamp(created_ts).strftime("%Y-%m-%d %H:%M")
        except Exception:
            created = ""
            created_ts = 0
        is_timer = os.path.exists(os.path.join(systempath, unit + ".timer"))
        rows.append({
            "unit": unit,
            "active": running,
            "enabled": enabled,
            "_is_timer": is_timer,
            "port_or_next": timers.get(unit, "") or port,
            "pid": pid_str,
            "cpu": cpu,
            "mem": mem,
            "restarts": str(restarts) if restarts else "",
            "exit": str(exit_status) if exit_status is not None else "",
            "log_24h": (str(log_lines) + ("+" if log_lines >= LOG_24H_CAP else "")) if log_lines else "",
            "env": env_vars,
            "last_log": last_log,
            "exec": exec_cmd,
            "cwd": cwd,
            "created": created,
            "_created_ts": created_ts,
        })

    SORT_DEFAULT = 0
    SORT_ALPHA = 1
    SORT_CREATED = 2
    sort_labels = ["Status", "A-Z", "Created"]

    def sort_rows(mode):
        """Sort rows. Timers always sort by next run; services sort by selected mode."""
        timers = [r for r in rows if r["_is_timer"]]
        services = [r for r in rows if not r["_is_timer"]]
        timers.sort(key=lambda x: x["port_or_next"] or "9999")
        if mode == SORT_DEFAULT:
            services.sort(key=lambda x: ("✓" not in x["active"], "✓" not in x["enabled"], x["unit"]))
        elif mode == SORT_ALPHA:
            services.sort(key=lambda x: x["unit"])
        elif mode == SORT_CREATED:
            services.sort(key=lambda x: x["_created_ts"], reverse=True)
        rows.clear()
        rows.extend(timers)
        rows.extend(services)

    sort_rows(SORT_DEFAULT)

    views = [
        [   # Status
            ("Unit", "unit"), ("Active", "active"), ("On boot", "enabled"),
            ("Next run OR Port", "port_or_next"), ("PID", "pid"),
            ("CPU%", "cpu"), ("Mem%", "mem"),
            ("CWD", "cwd"),
            ("Created", "created"), ("Env", "env"),
        ],
        [   # Detail
            ("Unit", "unit"), ("Active", "active"), ("On boot", "enabled"),
            ("Next run OR Port", "port_or_next"),
            ("Rst", "restarts"), ("Log 24h", "log_24h"),
            ("Exit", "exit"), ("Last log", "last_log"),
            ("Created", "created"),
        ],
        [   # Exec
            ("Unit", "unit"), ("Active", "active"), ("On boot", "enabled"),
            ("Next run OR Port", "port_or_next"),
            ("Exit", "exit"), ("Exec", "exec"),
            ("Created", "created"),
        ],
    ]

    view_labels = ["Status", "Detail", "Exec"]

    class UnitPicker(App):
        ENABLE_COMMAND_PALETTE = False
        BINDINGS = [
            Binding("t", "switch_view", "Toggle view", show=False),
            Binding("s", "cycle_sort", "Cycle sort", show=False),
            Binding("enter", "select_unit", "Select", show=False),
            Binding("q", "quit_app", "Quit", show=False),
        ]
        CSS = """
        Screen { background: transparent; }
        DataTable { height: 1fr; background: transparent; }
        DataTable > .datatable--header { background: transparent; color: $text; text-style: bold; }
        DataTable > .datatable--header-hover { background: transparent; color: $text; text-style: bold underline; }
        DataTable > .datatable--cursor { background: ansi_white; color: ansi_black; }
        #status-bar { height: 1; dock: bottom; background: transparent; }
        """

        def __init__(self):
            super().__init__()
            self.current_view = 0
            self.current_sort = SORT_DEFAULT
            self.selected_unit = None
            self.search_query = ""
            self.search_active = False

        def compose(self) -> ComposeResult:
            yield DataTable(cursor_type="row")
            yield Static(id="status-bar")

        def _update_status_bar(self):
            bar = self.query_one("#status-bar", Static)
            if self.search_active:
                bar.update("  [b]/[/]{}[reverse] [/]  │  [b]Esc[/] cancel  │  [b]Enter[/] confirm".format(
                    self.search_query))
            else:
                search_part = ""
                if self.search_query:
                    search_part = "  │  Filter: [yellow]{}[/] ([b]/[/] edit, [b]Esc[/] clear)".format(self.search_query)
                bar.update("  [b]t[/] View: {}  │  [b]s[/] Sort: {}{}  │  [b]enter[/] Select  │  [b]q[/] Quit".format(
                    view_labels[self.current_view], sort_labels[self.current_sort], search_part))

        def _filter_rows(self, row_list):
            if not self.search_query:
                return row_list
            q = self.search_query.lower()
            return [r for r in row_list if q in r["unit"].lower()]

        def _rebuild_table(self, reset_cursor=False):
            table = self.query_one(DataTable)
            cols = views[self.current_view]
            cursor_row = None if reset_cursor else table.cursor_row
            table.clear(columns=True)
            for label, _ in cols:
                table.add_column(label, key=label)
            timer_rows = self._filter_rows([r for r in rows if r["_is_timer"]])
            service_rows = self._filter_rows([r for r in rows if not r["_is_timer"]])
            self._row_index = []  # maps table row index -> rows index (None for separators)
            if timer_rows:
                sep_cells = [Text.from_markup("[bold]── Timers ──[/]")] + [Text("") for _ in cols[1:]]
                table.add_row(*sep_cells, key="__sep_timers")
                self._row_index.append(None)
                for row in timer_rows:
                    table.add_row(*[Text.from_markup(row[key]) for _, key in cols], key=row["unit"])
                    self._row_index.append(row)
            if timer_rows and service_rows:
                empty_cells = [Text("") for _ in cols]
                table.add_row(*empty_cells, key="__sep_empty")
                self._row_index.append(None)
            if service_rows:
                sep_cells = [Text.from_markup("[bold]── Services ──[/]")] + [Text("") for _ in cols[1:]]
                table.add_row(*sep_cells, key="__sep_services")
                self._row_index.append(None)
                for row in service_rows:
                    table.add_row(*[Text.from_markup(row[key]) for _, key in cols], key=row["unit"])
                    self._row_index.append(row)
            first_data = next((i for i, r in enumerate(self._row_index) if r is not None), 0)
            if cursor_row is not None and cursor_row < len(self._row_index) and self._row_index[cursor_row] is not None:
                table.move_cursor(row=cursor_row)
            else:
                table.move_cursor(row=first_data)
            self._update_status_bar()

        def on_mount(self):
            self._rebuild_table()

        def action_switch_view(self):
            self.current_view = (self.current_view + 1) % len(views)
            self._rebuild_table()

        def action_cycle_sort(self):
            self.current_sort = (self.current_sort + 1) % len(sort_labels)
            sort_rows(self.current_sort)
            self._rebuild_table()

        async def on_key(self, event):
            if self.search_active:
                if event.key == "escape":
                    self.search_active = False
                    self.search_query = ""
                    self._rebuild_table(reset_cursor=True)
                    event.stop()
                    event.prevent_default()
                elif event.key == "enter":
                    self.search_active = False
                    self._update_status_bar()
                    event.stop()
                    event.prevent_default()
                elif event.key == "backspace":
                    self.search_query = self.search_query[:-1]
                    self._rebuild_table(reset_cursor=True)
                    event.stop()
                    event.prevent_default()
                elif event.character and event.character.isprintable() and len(event.character) == 1:
                    self.search_query += event.character
                    self._rebuild_table(reset_cursor=True)
                    event.stop()
                    event.prevent_default()
            else:
                if event.key == "slash":
                    self.search_active = True
                    self.search_query = ""
                    self._update_status_bar()
                    event.stop()
                    event.prevent_default()
                elif event.key == "escape" and self.search_query:
                    self.search_query = ""
                    self._rebuild_table(reset_cursor=True)
                    event.stop()
                    event.prevent_default()

        def _get_selected_row(self, cursor_row):
            if cursor_row is not None and cursor_row < len(self._row_index):
                return self._row_index[cursor_row]
            return None

        def on_data_table_row_selected(self, event):
            row = self._get_selected_row(event.cursor_row)
            if row is not None:
                self.selected_unit = row["unit"]
                self.exit()

        def action_select_unit(self):
            table = self.query_one(DataTable)
            row = self._get_selected_row(table.cursor_row)
            if row is not None:
                self.selected_unit = row["unit"]
                self.exit()

        def action_quit_app(self):
            self.exit()

    app = UnitPicker()
    app.run()
    return app.selected_unit
