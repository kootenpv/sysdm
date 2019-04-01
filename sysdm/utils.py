import subprocess


def get_output(cmd):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True)
    (out, _) = proc.communicate()
    return out.decode().strip()


def is_unit_running(unit):
    return get_output('systemctl is-active {unit}'.format(unit=unit)) == "active"


def is_unit_enabled(unit):
    return get_output('systemctl is-enabled {unit}'.format(unit=unit)) == "enabled"
