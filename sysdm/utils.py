import subprocess


def get_output(cmd):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True)
    (out, _) = proc.communicate()
    return out.decode().strip()


def is_unit_running(unit):
    return get_output(f'systemctl is-active {unit}') == "active"
