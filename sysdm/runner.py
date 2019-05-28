import re
import time
import signal
from blessed import Terminal
from sysdm.utils import (
    get_output,
    is_unit_running,
    is_unit_enabled,
    read_ps_aux_by_unit,
    systemctl,
    journalctl,
)

from datetime import datetime, timedelta
from collections import deque


def run(unit, systempath):
    t = Terminal()
    print(t.enter_fullscreen())

    mapping = [
        "[R] Restart service                                                   ",
        "[S] Stop service                                                      ",
        "[T] Enable on startup                                                 ",
        "[G] Grep (filter) a pattern      [q] Quit view                        ",
    ]

    OFFSET = 12

    resized = [True]
    signal.signal(signal.SIGWINCH, lambda *args: resized.append(True))

    logo = "[sysdm]"
    # seen = set()

    Y_BANNER_OFFSET = len(mapping) + 1 + 2  # mapping, banner, in between lines

    grep = ""

    x_banner_offset = 0
    left_offset = 0
    log_offset = 0
    timer = None

    with t.hidden_cursor():
        try:
            while True:
                print(t.move(0, 0))
                y, x = t.get_location()
                if resized:
                    print(t.clear())
                    resized = []
                    timed = is_unit_running(unit + ".timer")
                    is_running = is_unit_running(unit) or timed
                    is_enabled = is_unit_enabled(unit)
                    if timed:
                        timer_text = ""
                        while not timer_text:
                            status = systemctl("list-timers " + unit + ".timer")
                            timer_text = status.split("\n")[1][4 : status.index("LEFT") - 2]
                        status = "Next: " + t.green(timer_text)
                        timer = datetime.strptime(timer_text, "%Y-%m-%d %H:%M:%S %Z")
                    else:
                        status = "Active: " + (t.green("✓") if is_running else t.red("✗"))
                    with t.location(OFFSET, 0):
                        enabled = t.green("✓") if is_enabled else t.red("✗")
                        line = "Unit: {} {} On Startup: {}".format(t.bold(unit), status, enabled)
                        x_banner_offset = len(line)
                        print(line)

                    with t.location(t.width - len(logo), 0):
                        print(t.bold(logo))

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

                # if timer just expired, refresh to get the new date
                if timer is not None and datetime.now() > timer:
                    resized = [True]
                if t.width - x_banner_offset > 50:
                    res = "| {} |".format(time.asctime())
                    if is_running:
                        ps_info = read_ps_aux_by_unit(systempath, unit)
                        if ps_info is not None:
                            res = "| {} | PID={} | CPU {:>4}% | MEM {:>4}%".format(
                                time.asctime(), *ps_info
                            )
                    with t.location(x_banner_offset, 0):
                        print(res)

                with t.location(0, Y_BANNER_OFFSET):
                    n = t.height - Y_BANNER_OFFSET - 1
                    w = t.width
                    g = "--grep " + grep if grep else ""
                    output = journalctl(
                        "-u {u} -u {u}_monitor -u {u}.timer -n {n} --no-pager {g}".format(
                            u=unit, n=n + log_offset + 100, g=g
                        )
                    )
                    outp = []
                    for line in output.split("\n"):
                        # replace e.g. python[pidnum123]: real output
                        line = re.sub("(?<=:\d\d ).+?\[\d+\]: ", "| ", line)
                        if grep:
                            rmatch = re.search(grep, line)
                            if rmatch is not None:
                                s = rmatch.start()
                                e = rmatch.end()
                                line = line[:s] + t.red(line[s:e]) + line[e:]
                        l = (line + " " * 200)[left_offset : w + left_offset - 5]
                        if "Stopped" in l:
                            l = t.bold(l)
                        if "Started" in l:
                            if timed:
                                ln = len(l)
                                white = " " * 200
                                l = (l.split("|")[0] + "| Succesfully ran on timer" + white)[:ln]
                            l = t.green(l)
                        if "WARNING: " in l:
                            l = t.yellow(l)
                        if "ERROR: " in l:
                            l = t.red(l)
                        if "Failed to start " in l:
                            l = t.red(l)
                        if "Triggering OnFailure= " in l:
                            l = t.yellow(l)
                        outp.append(l)
                    if log_offset:
                        print("\n".join(outp[-n - log_offset + 1 : -log_offset]))
                    else:
                        print("\n".join(outp[-n - log_offset + 1 :]))

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
                        systemctl("stop {unit}".format(unit=unit))
                        systemctl("stop {unit}.timer".format(unit=unit))
                    else:
                        print("Starting unit {unit}".format(unit=unit))
                        systemctl("start --no-block {unit}".format(unit=unit))
                        systemctl("start {unit}.timer".format(unit=unit))
                    resized = [True]
                elif inp == "R":
                    print(t.clear())
                    print("Restarting unit {unit}".format(unit=unit))
                    systemctl("restart {unit}".format(unit=unit))
                    resized = [True]
                elif inp == "T":
                    print(t.clear())
                    if is_enabled:
                        print("Disabling unit {unit} on startup".format(unit=unit))
                        systemctl("disable {unit}".format(unit=unit))
                        systemctl("disable {unit}.timer".format(unit=unit))
                    else:
                        print("Enabling unit {unit} on startup".format(unit=unit))
                        systemctl("enable {unit}".format(unit=unit))
                        systemctl("enable {unit}.timer".format(unit=unit))
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
                elif inp.name == "KEY_RIGHT":
                    print(t.erase())
                    left_offset = min(left_offset + 5, t.width)
                elif inp.name == "KEY_LEFT":
                    print(t.erase())
                    left_offset = max(0, left_offset - 5)
                elif inp.name == "KEY_UP":
                    print(t.erase())
                    log_offset = min(log_offset + 5, t.height)
                elif inp.name == "KEY_DOWN":
                    print(t.erase())
                    log_offset = max(0, log_offset - 5)
                else:
                    print(t.erase())
        except KeyboardInterrupt:
            pass
        print(t.clear())
