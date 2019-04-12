import re
import time
import signal
from blessed import Terminal
from sysdm.utils import get_output, is_unit_running, is_unit_enabled, read_ps_aux_by_unit


def run(unit, systempath):
    t = Terminal()
    print(t.enter_fullscreen())

    mapping = [
        "[R] Restart service                    [T] Enable on startup",
        "[S] Stop service                       [X] Toggle autorestart",
        "[q] Quit (keep running in background)  [X] Watch a new pattern",
        "[G] Grep (filter) a pattern            [X] Unwatch an existing pattern",
    ]

    OFFSET = 12

    resized = []
    signal.signal(signal.SIGWINCH, lambda *args: resized.append(True))

    logo = "[sysdm]"
    # seen = set()

    Y_BANNER_OFFSET = len(mapping) + 1 + 2  # mapping, banner, in between lines

    additional = ""
    grep = ""

    it = 0
    x_banner_offset = 0
    try:
        while True:
            y, x = t.get_location()
            # additional = "x={} y={}".format(x, y)
            if resized or it == 0 or y > t.height - 3:
                print(t.clear())
                resized = []
                it = 0
                is_running = is_unit_running(unit)
                is_enabled = is_unit_enabled(unit)
                with t.location(OFFSET, 0):
                    status = t.green("ACTIVE") if is_running else t.red("INACTIVE")
                    enabled = t.green("ENABLED") if is_enabled else t.red("DISABLED")
                    line = "Unit: {} Now: {} On Startup: {}".format(t.bold(unit), status, enabled)
                    x_banner_offset = len(line)
                    print(line)

                with t.location(t.width - len(logo + additional), 0):
                    print(t.bold(logo + additional))

                with t.location(0, 1):
                    print(t.center("-" * (t.width - 16)))

                for num, line in enumerate(mapping):
                    with t.location(0, num + 2):
                        if not is_running:
                            line = line.replace("Stop service ", "Start service")
                        if is_enabled:
                            line = line.replace("Enable on startup", "Disable on startup")
                        line = line.replace("[", "[" + t.green).replace("]", t.normal + "]")
                        print(" " * OFFSET + (line + " " * t.width)[: t.width + 3])

                with t.location(0, 6):
                    print(t.center("-" * (t.width - 16)))

            with t.hidden_cursor():

                if is_running and t.width - x_banner_offset > 50:
                    with t.location(x_banner_offset, 0):
                        ps_info = read_ps_aux_by_unit(systempath, unit)
                        if ps_info is not None:
                            res = "| {} | PID={} | CPU {:>4}% | MEM {:>4}% | NTHREADS={}".format(
                                time.asctime(), *ps_info
                            )
                            print(res)

            with t.hidden_cursor():
                with t.location(0, Y_BANNER_OFFSET):
                    n = t.height - Y_BANNER_OFFSET
                    w = t.width
                    g = "--grep " + grep if grep else ""
                    cmd = "journalctl -u {} -u {}_monitor -n {n} --no-pager --no-hostname {g}".format(
                        unit, unit, n=n + 50, g=g
                    )
                    output = get_output(cmd)
                    outp = []
                    for line in output.split("\n"):
                        if grep:
                            rmatch = re.search(grep, line)
                            if rmatch is not None:
                                s = rmatch.start()
                                e = rmatch.end()
                                line = line[:s] + t.red(line[s:e]) + line[e:]
                        l = (line + " " * 100)[: w - 5]
                        if "Stopped" in l:
                            l = t.red(l)
                        if "Started" in l:
                            l = t.green(l)
                        outp.append(l)
                    print("\n".join(outp[-n + 1 :]))

                with t.cbreak():
                    inp = t.inkey(0.3)

                if inp == "q":
                    if grep:
                        grep = ""
                    else:
                        break
                elif inp == "S":
                    print(t.clear())
                    if is_running:
                        print("Stopping unit {unit}".format(unit=unit))
                        get_output("systemctl stop {unit}".format(unit=unit))
                    else:
                        print("Starting unit {unit}".format(unit=unit))
                        get_output("systemctl start {unit}".format(unit=unit))
                    resized = [True]
                elif inp == "R":
                    print(t.clear())
                    print("Restarting unit {unit}".format(unit=unit))
                    get_output("systemctl restart {unit}".format(unit=unit))
                    resized = [True]
                elif inp == "T":
                    print(t.clear())
                    if is_enabled:
                        print("Disabling unit {unit} on startup".format(unit=unit))
                        get_output("systemctl disable {unit}".format(unit=unit))
                    else:
                        print("Enabling unit {unit} on startup".format(unit=unit))
                        get_output("systemctl enable {unit}".format(unit=unit))
                    resized = [True]
                elif inp == " ":
                    print(t.clear())
                    resized = [True]
                elif inp == "G":
                    print(t.clear())
                    if grep:
                        grep = ""
                    else:
                        grep = input(
                            "Grep pattern to search for (leave blank for cancel): "
                        ).strip()
                    resized = [True]
                else:
                    it += 1
                    print(t.erase())
    except KeyboardInterrupt:
        pass
    print(t.clear())
