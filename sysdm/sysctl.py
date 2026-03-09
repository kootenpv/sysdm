import re
import os
import sys
from cliche import cli
from sysdm.utils import (
    get_output,
    run_quiet,
    is_unit_running,
    is_unit_enabled,
    to_sn,
    systemctl,
    get_sysdm_executable,
    IS_SUDO,
    linger,
)

USER_AND_GROUP = None


def user_and_group_if_sudo(root):
    global USER_AND_GROUP
    if USER_AND_GROUP is not None:
        return USER_AND_GROUP
    else:
        if IS_SUDO:
            if root:
                user = "root"
                user_group = get_output("""getent group | grep :0: | awk -F ":" '{ print $1}'""").split("\n")[0]
            else:
                user = get_output("echo $SUDO_USER")
                user_group = get_output("""getent group | grep $SUDO_GID: | awk -F ":" '{ print $1}'""").split("\n")[0]
            output = "User={user}\nGroup={user_group}".format(user=user, user_group=user_group)
        else:
            output = ""
    USER_AND_GROUP = output
    return output


def contains_python(fname):
    fname_cmd = get_output("which " + fname)
    if os.path.exists(fname_cmd):
        with open(fname_cmd) as f:
            return "python" in f.read()
    return False


def get_version_tuple(py):
    out = get_output(f"{py} --version")
    if out.startswith("Python"):
        return tuple(int(x) for x in out.split()[-1].split("."))
    return (0, 0, 0)


def get_cmd_from_filename(fname):
    cmd = None
    binary = False
    if fname.endswith(".py"):
        cmd3, cmd = get_output("which python3"), get_output("which python")
        if get_version_tuple(cmd3) > get_version_tuple(cmd):
            cmd = cmd3
    elif fname.endswith(".sh"):
        cmd = get_output("which bash")
    elif fname.endswith(".js"):
        cmd = get_output("which node")
    else:
        if "." in fname.split("/")[-1]:
            tmpl = "WARNING: File extension of file '{}' not supported. Treating as executable."
            print(tmpl.format(fname))
        if os.path.isfile(fname):
            cmd = os.path.abspath(fname)
        else:
            cmd = get_output("which " + fname)
            if not cmd:
                return binary, None
        binary = True
    return binary, cmd.strip()


def get_extensions_from_filename(fname):
    cmd = []
    if "." in fname.split("/")[-1]:
        cmd = ["." + fname.split(".")[-1]]
    elif os.path.isfile(fname):
        cmd = [fname]
    elif contains_python(fname):
        cmd = [".py"]
    return cmd


def get_exclusions_from_filename(fname):
    cmd = []
    if fname.endswith(".py"):
        cmd = ["flycheck_", "$", ".vim", "'#'", ".swp"]
    elif fname.endswith(".sh"):
        cmd = []
    elif fname.endswith(".js"):
        cmd = ["flycheck_", "$", ".vim", "'#'", ".swp"]
    return cmd


def get_service_name(fname_or_cmd):
    items = fname_or_cmd.split()
    name = items[0]
    if len(items) > 1 and re.search("[a-z]", items[1]):
        name += "_" + items[1]
    return name


def create_service_template(
    fname_or_cmd, notifier, timer, delay, root, killaftertimeout, restart, workdir: str = "", env_vars=[]
):
    here = workdir or os.path.abspath(".")
    fname, extra_args = fname_or_cmd.split()[0], " ".join(fname_or_cmd.split()[1:])
    binary, cmd = get_cmd_from_filename(fname)
    if cmd is None:
        # shell builtin or complex command — wrap with bash -c
        # systemd ExecStart uses its own quoting: double quotes with \\ and \" escapes, %% for literal %
        escaped = fname_or_cmd.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
        cmd = '/bin/bash -c "' + escaped + '"'
        binary = True
        extra_args = ""
    service_name = get_service_name(fname_or_cmd) + "_" + here.split("/")[-1] if binary else fname
    service_name = to_sn(service_name)
    fname = fname + " "
    start_info = ""
    # other binary
    if binary:
        fname = ""
    if notifier is not None:
        on_failure = "OnFailure={}-onfailure@%i.service".format(notifier)
    else:
        on_failure = ""
    if timer is not None:
        if isinstance(timer, str):
            timer = [timer]
        validated = [run_quiet("systemd-analyze calendar '{}'".format(t)) for t in timer]
        timer = [v for v in validated if bool(v)] or None
    if bool(timer):
        service_type = "oneshot"
        restart = ""
        part_of = ""
    else:
        service_type = "simple"
        start_info = "StartLimitBurst=2\nStartLimitIntervalSec=15s" if restart else ""
        restart = "Restart=always\nRestartSec={delay}".format(delay=delay) if restart else ""
        part_of = "PartOf={service_name}_monitor.service".format(service_name=service_name)
    user_and_group = user_and_group_if_sudo(root)
    if timer:
        install = ""
    else:
        wanted_by = "multi-user.target" if user_and_group.strip() else "default.target"
        wanted_by += " " + service_name + "_monitor.service"
        install = "[Install]\nWantedBy={wanted_by}".format(wanted_by=wanted_by)
    env_var_section = "\n".join([f'Environment={x if "=" in x else x + "=" + os.environ[x]}' for x in env_vars])
    service = (
        """
    [Unit]
    Description={service_name} service (generated by sysdm)
    After=network-online.target
    {part_of}
    {on_failure}
    {start_info}

    [Service]
    {user_and_group}
    Type={service_type}
    {restart}
    TimeoutStopSec={killaftertimeout}
    ExecStart={cmd} {fname} {extra_args}
    WorkingDirectory={here}
    Environment=PYTHONUNBUFFERED=1
    {env_var_section}

    {install}
    """.replace(
            "\n    ", "\n"
        )
        .format(**locals())
        .strip()
    )
    return service_name, service


def timer_granularity(timer_str):
    if timer_str.count(":") == 2:
        if timer_str.endswith("*"):
            return "1s"
        else:
            return "10s"
    return "1m"


def create_timer_service(systempath, service_name, timer):
    if timer is None:
        return False
    if isinstance(timer, str):
        timer = [timer]
    validated = []
    for t in timer:
        output = run_quiet("systemd-analyze calendar '{}'".format(t))
        if not bool(output):
            print("Invalid timer expression: '{}'".format(t))
            continue
        validated.append((t, output))
    if not validated:
        print("Service type 'simple' (long running) since NOT using a timer.")
        return False
    # use the earliest next run for display
    next_runs = [v.split("From now: ")[1].strip() for _, v in validated]
    accuracy_sec = timer_granularity(validated[0][1])
    print("Service type 'oneshot' since using a timer. Next run: {}".format(next_runs[0]))
    on_calendar = "\n".join("OnCalendar={}".format(t) for t, _ in validated)
    service = (
        """
    [Unit]
    Description=Running '{service_name}' on a schedule (generated by sysdm)

    [Timer]
    {on_calendar}
    AccuracySec={accuracy_sec}

    [Install]
    WantedBy=timers.target

    """.replace(
            "\n    ", "\n"
        )
        .format(service_name=service_name, on_calendar=on_calendar, accuracy_sec=accuracy_sec)
        .strip()
    )
    with open(os.path.join(systempath, "{}.timer".format(service_name)), "w") as f:
        f.write(service)
    return True


def create_service_monitor_template(service_name, fname_or_cmd, extensions, exclude_patterns, root):
    cmd = get_sysdm_executable()
    here = os.path.abspath(".")
    fname = fname_or_cmd.split()[0]
    extensions = extensions or get_extensions_from_filename(fname)
    extensions = "--extensions " + " ".join(extensions) if extensions else ""
    exclude_patterns = exclude_patterns or get_exclusions_from_filename(fname)
    exclude_patterns = " ".join(exclude_patterns)
    exclude_patterns = "--exclude_patterns " + exclude_patterns if exclude_patterns else ""
    user_and_group = user_and_group_if_sudo(root)
    wanted_by = "multi-user.target" if user_and_group.strip() else "default.target"
    service = (
        """
    [Unit]
    Description={service_name}.monitor service (generated by sysdm)
    After=network-online.target

    [Service]
    {user_and_group}
    Type=simple
    Restart=always
    RestartSec=0
    Environment="PYTHONUNBUFFERED=on"
    ExecStart={cmd} file_watch {extensions} {exclude_patterns}
    WorkingDirectory={here}

    [Install]
    WantedBy={wanted_by}
    """.replace(
            "\n    ", "\n"
        )
        .format(
            service_name=service_name,
            cmd=cmd,
            extensions=extensions,
            exclude_patterns=exclude_patterns,
            here=here,
            user_and_group=user_and_group,
            wanted_by=wanted_by,
        )
        .strip()
    )
    return service


def create_notification_on_failure_service(
    systempath, service_name, n_notifier, n_user, n_to, n_pw, n_msg, n_status_cmd, root
):
    if n_notifier is None:
        return
    notify = get_sysdm_executable() + " notify"
    user = get_output("echo $USER")
    home = get_output("echo ~" + user)
    host = get_output("echo $HOSTNAME")
    n_msg = n_msg.format(home=home, host=host)
    exec_start = f"""/bin/bash -c "{n_status_cmd} | {notify} {n_notifier} -m {n_msg!r}"""
    if n_user is not None:
        exec_start += f" -u {n_user!r}"
    if n_to is not None:
        exec_start += f" -t {n_to!r}"
    if n_pw is not None:
        exec_start += f" -p {n_pw!r}"
    exec_start += '"'
    print("Testing notifier ({})".format(n_notifier))
    test_cmd = exec_start.replace("%i", service_name).replace("%H", host).replace("failed on", "test succeeded on")
    print(test_cmd)
    outp = get_output(test_cmd)
    if "Fault" in outp or "invalid" in outp:
        print(outp)
        sys.exit(1)
    print("")
    print("Test succeeded.")
    service = """
    [Unit]
    Description={notify_cmd} OnFailure for %i

    [Service]
    {user_and_group}
    Type=oneshot
    ExecStart={exec_start}
    """.replace(
        "\n    ", "\n"
    ).format(
        exec_start=exec_start,
        notify_cmd=n_notifier,
        user_and_group=user_and_group_if_sudo(root),
    )
    with open(os.path.join(systempath, "{}-onfailure@.service".format(n_notifier)), "w") as f:
        f.write(service)


def show(systempath, unit):
    service_name = unit
    service_file = os.path.join(systempath, service_name) + ".service"
    service_monitor_file = os.path.join(systempath, service_name) + "_monitor.service"
    service_timer_file = os.path.join(systempath, service_name) + ".timer"
    print("--- CONTENTS FOR {} ---".format(service_file))
    with open(service_file, "r") as f:
        print(f.read())
    try:
        with open(service_monitor_file, "r") as f:
            print("\n--- CONTENTS FOR {} ---".format(service_monitor_file))
            print(f.read())
    except FileNotFoundError:
        pass
    try:
        with open(service_timer_file, "r") as f:
            print("\n--- CONTENTS FOR {} ---".format(service_timer_file))
            print(f.read())
    except FileNotFoundError:
        pass


def ls(systempath):
    units = []
    for fname in sorted(os.listdir(systempath)):
        if "_monitor.s" in fname or fname.endswith(".timer"):
            continue
        fpath = systempath + "/" + fname
        if os.path.isdir(fpath):
            continue
        with open(fpath) as f:
            if "generated by " in f.read():
                units.append(fname.replace(".service", ""))
    return units


def stop_and_disable(unit_name):
    """Stop and disable a unit's services. Returns list of (name, before_enabled, before_active, after_enabled, after_active)."""
    rows = []
    for s in [unit_name, unit_name + "_monitor", unit_name + ".timer"]:
        before_enabled = is_unit_enabled(s)
        before_active = is_unit_running(s)
        if before_enabled:
            systemctl("disable {}".format(s))
        if before_active:
            systemctl("stop {}".format(s))
        after_enabled = is_unit_enabled(s)
        after_active = is_unit_running(s)
        rows.append((s, before_enabled, before_active, after_enabled, after_active))
    return rows


def print_status_table(rows):
    """Print a before/after status table for unit operations."""
    check = "✓"
    cross = "✗"
    c = max(len(r[0]) for r in rows)
    e, a = 9, 8  # column widths for Enabled/Active

    def val(v):
        return check if v else cross

    top    = "┌" + "─" * (c + 2) + "┬" + "─" * (e + a + 3) + "┬" + "─" * (e + a + 3) + "┐"
    mid    = "├" + "─" * (c + 2) + "┼" + "─" * (e + a + 3) + "┼" + "─" * (e + a + 3) + "┤"
    bottom = "└" + "─" * (c + 2) + "┴" + "─" * (e + a + 3) + "┴" + "─" * (e + a + 3) + "┘"

    print(top)
    print("│ {} │ {:^{}} │ {:^{}} │".format("Unit".ljust(c), "Before", e + a + 1, "After", e + a + 1))
    print("│ {} │ {:^{}} {:^{}} │ {:^{}} {:^{}} │".format(
        " " * c, "Enabled", e, "Active", a, "Enabled", e, "Active", a))
    print(mid)
    for name, be, ba, ae, aa in rows:
        print("│ {} │ {:^{}} {:^{}} │ {:^{}} {:^{}} │".format(
            name.ljust(c), val(be), e, val(ba), a, val(ae), e, val(aa), a))
    print(bottom)


def delete(unit, systempath):
    service_name = unit.replace(".", "_")
    path = systempath + "/" + service_name
    rows = stop_and_disable(service_name)
    print_status_table(rows)
    _ = systemctl("daemon-reload")
    for suffix in [".service", "_monitor.service", ".timer"]:
        run_quiet("rm {}".format(path + suffix))
    print("Delete Succeeded!")


@cli
def reload():
    """Reload systemd daemon configuration"""
    systemctl("daemon-reload")


# if doing start on a bla.timer, then dont do start on the bla.service itself
