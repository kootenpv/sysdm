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
    return systemctl('is-enabled {unit}'.format(unit=unit)) == "enabled"


def read_command_from_unit(systempath, service_name):
    with open(os.path.join(systempath, service_name) + ".service") as f:
        for line in f.read().split("\n"):
            if line.startswith("ExecStart="):
                return line[10:].strip()


def read_ps_aux_by_unit(systempath, unit, ps_aux):
    cmd = read_command_from_unit(systempath, unit)
    for num, line in enumerate(ps_aux.split("\n")):
        if num == 0:
            continue
        pid, cpu, mem, ppid, *rest = line.split()
        # # I think this was here because of sudo?
        # if ppid != "1":
        #     continue
        rest = " ".join(rest)
        if cmd.endswith(rest) or rest.endswith(cmd):
            return pid, cpu, mem


def get_port_from_ps_and_ss(pid, ss):
    result = None
    for line in ss.split("\n"):
        if "," + pid + "," in line or "pid=" + pid + "," in line:
            result = line.split()[4]
    return result or ""


def is_git_ignored(abspath):
    return bool(get_output("git check-ignore {}".format(abspath)).strip())


def to_sn(fname_or_cmd):
    return fname_or_cmd.split()[0].split("/")[-1].replace(".", "_")


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
