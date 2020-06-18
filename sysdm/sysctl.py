import os
import sys
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


def user_and_group_if_sudo(args):
    global USER_AND_GROUP
    if USER_AND_GROUP is not None:
        return USER_AND_GROUP
    else:
        if IS_SUDO:
            if args.root:
                user = "root"
                user_group = get_output(
                    """getent group | grep :0: | awk -F ":" '{ print $1}'"""
                ).split("\n")[0]
            else:
                user = get_output("echo $SUDO_USER")
                user_group = get_output(
                    """getent group | grep $SUDO_GID: | awk -F ":" '{ print $1}'"""
                ).split("\n")[0]
            output = "User={user}\nGroup={user_group}".format(user=user, user_group=user_group)
        else:
            output = ""
    USER_AND_GROUP = output
    return output


def get_cmd_from_filename(fname):
    cmd = None
    binary = False
    if fname.endswith(".py"):
        cmd = (get_output("which python3") or get_output("which python")) + " -u"
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
                print("Do not understand how to run '{}'".format(fname))
                sys.exit(1)
        binary = True
    return binary, cmd.strip()


def get_extensions_from_filename(fname):
    cmd = []
    if "." in fname.split("/")[-1]:
        cmd = ["." + fname.split(".")[-1]]
    elif os.path.isfile(fname):
        cmd = [fname]
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


def create_service_template(args):
    here = os.path.abspath(".")
    fname, extra_args = args.fname_or_cmd.split()[0], " ".join(args.fname_or_cmd.split()[1:])
    binary, cmd = get_cmd_from_filename(fname)
    service_name = fname + "_" + here.split("/")[-1] if binary else fname
    service_name = to_sn(service_name)
    fname = fname + " "
    # other binary
    if binary:
        fname = ""
    if args.notify_cmd != "-1":
        on_failure = "OnFailure={}-onfailure@%i.service".format(args.notify_cmd)
    else:
        on_failure = ""
    timer = run_quiet("systemd-analyze calendar '{}'".format(args.timer))
    if bool(timer):
        service_type = "oneshot"
        restart = ""
        part_of = ""
    else:
        service_type = "simple"
        restart = "Restart=always\nRestartSec={delay}".format(delay=args.delay)
        part_of = "PartOf={service_name}_monitor.service".format(service_name=service_name)
    user_and_group = user_and_group_if_sudo(args)
    if timer:
        install = ""
    else:
        wanted_by = "multi-user.target" if user_and_group.strip() else "default.target"
        install = "[Install]\nWantedBy={wanted_by}".format(wanted_by=wanted_by)
    bool(timer)
    service = (
        """
    [Unit]
    Description={service_name} service (generated by sysdm)
    After=network-online.target
    {part_of}
    {on_failure}

    [Service]
    {user_and_group}
    Type={service_type}
    {restart}
    ExecStart={cmd} {fname} {extra_args}
    WorkingDirectory={here}

    {install}
    """.replace(
            "\n    ", "\n"
        )
        .format(
            service_name=service_name,
            cmd=cmd,
            fname=fname,
            extra_args=extra_args,
            here=here,
            restart=restart,
            part_of=part_of,
            on_failure=on_failure,
            service_type=service_type,
            user_and_group=user_and_group,
            install=install,
        )
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


def create_timer_service(service_name, args):
    timer = run_quiet("systemd-analyze calendar '{}'".format(args.timer))
    if not bool(timer):
        print("Service type 'simple' (long running) since NOT using a timer.")
        return False
    next_run = timer.split("From now: ")[1].strip()
    accuracy_sec = timer_granularity(args.timer)
    print("Service type 'oneshot' since using a timer. Next run: {}".format(next_run))
    service = (
        """
    [Unit]
    Description=Running '{service_name}' on a schedule (generated by sysdm)
    Requires={service_name}.service

    [Timer]
    OnCalendar={timer}
    AccuracySec={accuracy_sec}

    [Install]
    WantedBy=timers.target

    """.replace(
            "\n    ", "\n"
        )
        .format(timer=args.timer, service_name=service_name, accuracy_sec=accuracy_sec)
        .strip()
    )
    with open(os.path.join(args.systempath, "{}.timer".format(service_name)), "w") as f:
        f.write(service)
    return True


def create_service_monitor_template(service_name, args):
    cmd = get_sysdm_executable()
    here = os.path.abspath(".")
    fname = args.fname_or_cmd.split()[0]
    extensions = args.extensions or get_extensions_from_filename(fname)
    extensions = " ".join(extensions)
    exclude_patterns = args.exclude_patterns or get_exclusions_from_filename(fname)
    exclude_patterns = " ".join(exclude_patterns)
    exclude_patterns = "--exclude_patterns " + exclude_patterns if exclude_patterns else ""
    user_and_group = user_and_group_if_sudo(args)
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
    ExecStart={cmd} watch {extensions} {exclude_patterns}
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


def create_mail_on_failure_service(args):
    if args.notify_cmd == "-1":
        return
    notifier = get_output("which " + args.notify_cmd)
    user = get_output("echo $USER")
    home = get_output("echo ~" + user)
    host = get_output("echo $HOSTNAME")
    notify_cmd_args = args.notify_cmd_args.format(home=home, host=host)
    exec_start = """/bin/bash -c '{notify_status_cmd} | {notifier} {notify_cmd_args}' """.format(
        notify_status_cmd=args.notify_status_cmd, notifier=notifier, notify_cmd_args=notify_cmd_args
    )
    print("Testing notifier ({})".format(args.notify_cmd))
    test_args = (
        args.notify_cmd_args.replace("%i", args.notify_cmd)
        .replace("failed", "test succeeded")
        .replace("%H", host)
        .format(home=home, host=host)
    )
    test_cmd = """/bin/bash -c '{notify_status_cmd} | {notifier} {notify_cmd_args}' """.format(
        notify_status_cmd=args.notify_status_cmd.replace("%i", ""),
        notifier=notifier,
        notify_cmd_args=test_args,
    )
    print(get_output(test_cmd))
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
        notify_cmd=args.notify_cmd,
        user_and_group=user_and_group_if_sudo(args),
    )
    with open(
        os.path.join(args.systempath, "{}-onfailure@.service".format(args.notify_cmd)), "w"
    ) as f:
        f.write(service)


def install(args):
    service_name, service = create_service_template(args)
    try:
        with open(os.path.join(args.systempath, service_name) + ".service", "w") as f:
            print(service)
            f.write(service)
    except PermissionError:
        print("Need sudo to create systemd unit service file.")
        sys.exit(1)
    create_mail_on_failure_service(args)
    _ = systemctl("daemon-reload")
    create_timer = create_timer_service(service_name, args)
    if create_timer:
        _ = systemctl("enable {}.timer".format(service_name))
        _ = systemctl("start {}.timer".format(service_name))
    else:
        _ = systemctl("enable {}".format(service_name))
        monitor = create_service_monitor_template(service_name, args)
        with open(os.path.join(args.systempath, service_name) + "_monitor.service", "w") as f:
            f.write(monitor)
        _ = systemctl("start --no-block {}".format(service_name))
        _ = systemctl("enable {}_monitor".format(service_name))
        _ = systemctl("start {}_monitor".format(service_name))
    print(linger())
    return service_name


def show(args):
    service_name = args.unit
    service_file = os.path.join(args.systempath, service_name) + ".service"
    service_monitor_file = os.path.join(args.systempath, service_name) + "_monitor.service"
    service_timer_file = os.path.join(args.systempath, service_name) + ".timer"
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


def ls(args):
    units = []
    for fname in os.listdir(args.systempath):
        if "_monitor.s" in fname or fname.endswith(".timer"):
            continue
        fpath = args.systempath + "/" + fname
        if os.path.isdir(fpath):
            continue
        with open(fpath) as f:
            if "generated by " in f.read():
                units.append(fname.replace(".service", ""))
    return units


def delete(unit, systempath):
    service_name = unit.replace(".", "_")
    path = systempath + "/" + service_name
    for s in [service_name, service_name + "_monitor", service_name + ".timer"]:
        if is_unit_enabled(s):
            _ = systemctl("disable {}".format(s))
            print("Disabled unit {}".format(s))
        else:
            print("Unit {} was not enabled so no need to disable it".format(s))
        if is_unit_running(s):
            _ = systemctl("stop {}".format(s))
            print("Stopped unit {}".format(s))
        else:
            print("Unit {} was not started so no need to stop it".format(s))
    _ = systemctl("daemon-reload")
    o = run_quiet("rm {}".format(path + ".service"))
    o = run_quiet("rm {}".format(path + "_monitor.service"))
    o = run_quiet("rm {}".format(path + ".timer"))
    print("Deleted {}".format(path + ".service"))
    print("Deleted {}".format(path + "_monitor.service"))
    print("Deleted {}".format(path + ".timer"))
    print("Delete Succeeded!")


# if doing start on a bla.timer, then dont do start on the bla.service itself
