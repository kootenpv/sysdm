import sys
import os
from sysdm.sysctl import install, show, ls, delete
from sysdm.file_watcher import watch
from sysdm.utils import get_output, is_unit_running, is_unit_enabled
from sysdm.runner import run
from pick import Picker


def get_argparser(args=None):
    """ This is the function that is run from commandline with `chist` """
    import argparse

    parser = argparse.ArgumentParser(description='sysdm')
    subparsers = parser.add_subparsers(dest="command")
    create = subparsers.add_parser('create')
    create.add_argument(
        '--systempath', default="/etc/systemd/system", help='Folder where to save the service file'
    )
    create.add_argument(
        '--norestart', action='store_true', help='Whether to prevent auto restart on error'
    )
    create.add_argument('fname', help='File/cmd to run')
    create.add_argument('extra_args', help='File to run', nargs="*")
    create.add_argument(
        '--delay', '-d', default=0.1, help='Set a delay in the unit file before attempting restart.'
    )
    create.add_argument(
        '--extensions', '-w', help='Patterns of files to watch (by default inferred)', nargs='+'
    )
    create.add_argument(
        '--exclude_patterns', help='Patterns of files to ignore (by default inferred)', nargs='+'
    )
    view = subparsers.add_parser('view')
    view.add_argument(
        '--systempath', default="/etc/systemd/system", help='Folder where to look for service files'
    )
    view.add_argument('fname', help='File/cmd/unit to observe')
    show_unit = subparsers.add_parser('show_unit')
    show_unit.add_argument(
        '--systempath', default="/etc/systemd/system", help='Folder where to look for service files'
    )
    show_unit.add_argument('fname', help='File/cmd/unit to show service')
    watch = subparsers.add_parser('watch')
    watch.add_argument(
        'extensions', help='Patterns of files to watch (by default inferred)', nargs='?'
    )
    watch.add_argument(
        '--exclude_patterns', help='Patterns of files to ignore (by default inferred)', nargs='+'
    )
    ls = subparsers.add_parser('ls')
    ls.add_argument(
        '--systempath', default="/etc/systemd/system", help='Folder where to look for service files'
    )
    delete = subparsers.add_parser('delete')
    delete.add_argument(
        '--systempath', default="/etc/systemd/system", help='Folder where to look for service files'
    )
    delete.add_argument('fname', nargs="?", help='File/cmd/unit to observe')
    return parser, parser.parse_args(args)


def choose_unit(units):
    options = []
    for unit in units:
        is_running = is_unit_running(unit)
        is_enabled = is_unit_enabled(unit)
        running = "✓" if is_running else "✗"
        enabled = "✓" if is_enabled else "✗"
        options.append((unit, running, enabled))

    pad = "{}|    {}    |    {}   "
    offset = max([len(x[0]) for x in options]) + 3
    formatted_options = [pad.format(x.ljust(offset), r, e) for x, r, e in options]
    quit = "-- Quit --"
    formatted_options.append(" ")
    formatted_options.append(quit)
    title = "These are known units:\n\n{}| Running | Starts on boot".format(" " * (offset + 2))
    default_index = 0
    while True:
        p = Picker(formatted_options, title, default_index=default_index)
        p.register_custom_handler(ord('q'), lambda _: sys.exit(0))
        chosen, index = p.start()
        if chosen == quit:
            return None
        elif chosen == " ":
            default_index = index
            continue
        else:
            break
    return units[index]


def main():
    parser, args = get_argparser()
    if args.command == "create":
        print("Creating systemd unit...")
        install(args)
        print("Done")
    elif args.command == "view":
        service_name = args.fname.replace(".", "_")
        if not os.path.exists(args.systempath + "/" + service_name + ".service"):
            print(
                "Service file does not exist. You can start by running:\n\n    sudo sysdm create {}\n\nto create a service or run:\n\n    sysdm ls\n\nto see the services already created by sysdm.".format(
                    args.fname
                )
            )
            sys.exit(1)
        run(service_name, args.systempath)
    elif args.command == "show_unit":
        show(args)
    elif args.command == "watch":
        watch(args)
    elif args.command == "delete":
        sudo = get_output("echo $SUDO_USER")
        if not sudo:
            print("Need sudo to delete systemd unit files.")
            sys.exit(1)
        if args.fname is None:
            units = ls(args)
            unit = choose_unit(units)
            inp = input("Are you sure you want to delete '{}'? [y/N]: ".format(unit))
            if inp.lower().strip() != "y":
                print("Aborting")
                return
        else:
            unit = args.fname
        delete(unit, args.systempath)
    elif args.command == "ls":
        units = ls(args)
        if units:
            unit = choose_unit(units)
            if unit is None:
                sys.exit()
            run(unit, args.systempath)
        else:
            print(
                "sysdm knows of no units. Why don't you make one? `sudo sysdm create file_i_want_to_service.py`"
            )

    else:
        parser.print_help(sys.stderr)
        sys.exit(1)
