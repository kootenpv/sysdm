import sys
import os
import subprocess


def get_output(cmd):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True)
    (out, _) = proc.communicate()
    return out.decode().strip()


def run_quiet(cmd):
    with open(os.devnull, 'w') as devnull:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=devnull, shell=True)
        (out, _) = proc.communicate()
        return out.decode().strip()


def is_unit_running(unit):
    return systemctl('is-active {unit}'.format(unit=unit)) == "active"


def is_unit_enabled(unit):
    return systemctl('is-enabled {unit} 2> /dev/null'.format(unit=unit)) == "enabled"


def read_command_from_unit(systempath, service_name):
    with open(os.path.join(systempath, service_name) + ".service") as f:
        for line in f.read().split("\n"):
            if line.startswith("ExecStart="):
                return line[10:].strip()


def batch_systemctl_show(units, properties):
    """Query multiple properties for multiple units in a single systemctl show call.

    Returns dict of {unit: {property: value}}. Output blocks are separated by blank
    lines and appear in the same order as the input units.
    """
    if not units:
        return {}
    cmd = "sudo systemctl " if IS_SUDO else "systemctl --user "
    cmd += "show --no-pager"
    for p in properties:
        cmd += " -p " + p
    for u in units:
        cmd += " " + u
    out = run_quiet(cmd)
    blocks = out.split("\n\n")
    result = {}
    for unit, block in zip(units, blocks):
        info = {}
        for line in block.split("\n"):
            if "=" in line:
                k, v = line.split("=", 1)
                info[k] = v
        result[unit] = info
    return result


def read_ps_aux_by_unit(systempath, unit, ps_aux, main_pid=None):
    # Get MainPID from systemd — reliable regardless of how the process appears in ps
    if main_pid is None:
        main_pid = systemctl("show {} -p MainPID --value".format(unit)).strip()
    if main_pid and main_pid != "0":
        for num, line in enumerate(ps_aux.split("\n")):
            if num == 0:
                continue
            parts = line.split()
            if len(parts) >= 3 and parts[0] == main_pid:
                return parts[0], parts[1], parts[2]
    # Fallback: match by command
    cmd = read_command_from_unit(systempath, unit)
    for num, line in enumerate(ps_aux.split("\n")):
        if num == 0:
            continue
        pid, cpu, mem, ppid, *rest = line.split()
        rest = " ".join(rest)
        if cmd and (cmd.endswith(rest) or rest.endswith(cmd)):
            return pid, cpu, mem


def get_child_pids(pid, ps_aux):
    """Get all descendant PIDs of a given PID."""
    children = {}
    for num, line in enumerate(ps_aux.split("\n")):
        if num == 0:
            continue
        parts = line.split()
        if len(parts) >= 4:
            children.setdefault(parts[3], []).append(parts[0])
    result = set()
    queue = [pid]
    while queue:
        p = queue.pop()
        for child in children.get(p, []):
            if child not in result:
                result.add(child)
                queue.append(child)
    return result


def get_port_from_ps_and_ss(pid, ss, ps_aux=None):
    pids = {pid}
    if ps_aux:
        pids |= get_child_pids(pid, ps_aux)
    results = []
    for line in ss.split("\n"):
        for p in pids:
            if "," + p + "," in line or "pid=" + p + "," in line:
                results.append(line.split()[4])
    if not results:
        return ""
    # Prefer IPv4 over IPv6
    for r in results:
        if not r.startswith("["):
            return r
    return results[0]


def is_git_ignored(abspath):
    return bool(get_output("git check-ignore {}".format(abspath)).strip())


def to_sn(fname_or_cmd):
    import re
    name = fname_or_cmd.split()[0].split("/")[-1].replace(".", "_")
    return re.sub(r"[^a-zA-Z0-9_:-]", "", name)


def systemctl(rest):
    cmd = "sudo systemctl " if IS_SUDO else "systemctl --user "
    cmd += rest
    return get_output(cmd)


def linger():
    if not IS_SUDO:
        return get_output("loginctl enable-linger $USER")


def journalctl(cmd):
    return get_output(cmd)


def get_sysdm_executable():
    executable = [x for x in sys.argv if x.endswith("/sysdm")]
    executable = executable[0] if executable else get_output("which sysdm")
    return executable


IS_SUDO = bool(get_output("echo $SUDO_USER"))
