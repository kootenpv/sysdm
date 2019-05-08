import sys
import os
from pick import Picker
from sysdm.sysctl import install, show, ls, delete
from sysdm.file_watcher import watch
from sysdm.utils import get_output, is_unit_running, is_unit_enabled, to_sn
from sysdm.runner import run


def get_argparser(args=None):
    """ This is the function that is run from commandline with `chist` """
    import argparse

    parser = argparse.ArgumentParser(description='sysdm')

    subparsers = parser.add_subparsers(dest="command")
    create = subparsers.add_parser('create')
    create.add_argument(
        '--systempath',
        default="~/.config/systemd/user",
        help='Folder where to save the service file, default: %(default)s',
    )
    create.add_argument(
        '--norestart', action='store_true', help='Whether to prevent auto restart on error'
    )
    create.add_argument('fname_or_cmd', help='File/cmd to run')
    create.add_argument(
        '--delay',
        '-d',
        default=0.2,
        help='Set a delay in the unit file before attempting restart, default: %(default)s',
    )
    create.add_argument(
        '--extensions', '-w', help='Patterns of files to watch (by default inferred)', nargs='+'
    )
    create.add_argument(
        '--exclude_patterns', help='Patterns of files to ignore (by default inferred)', nargs='+'
    )
    create.add_argument(
        '--notify_cmd',
        default="yagmail",
        help='Binary command that will notify. Setting this to -1 will add no notifier, default: %(default)s',
    )
    create.add_argument(
        '--notify_status_cmd',
        default="systemctl --user status -l -n 1000 %i",
        help='Command that echoes output to the notifier on failure, default: %(default)s',
    )
    create.add_argument(
        '--notify_cmd_args',
        default='-s "%i failed on %H" -oauth2 {home}/oauth2.json',
        help='Arguments passed to notify command. \n\nDefault: %(default)s. (default assumes OAuth2 gmail backend. See yagmail for details.)',
    )
    create.add_argument(
        '--timer',
        default='None',
        help='Used to set timer. Checked to be valid. E.g. *-*-* 03:00:00 for daily at 3 am.',
    )
    view = subparsers.add_parser('view')
    view.add_argument(
        '--systempath',
        default="~/.config/systemd/user",
        help='Folder where to look for service files',
    )
    view.add_argument('unit', help='File/cmd/unit to observe')
    show_unit = subparsers.add_parser('show_unit')
    show_unit.add_argument(
        '--systempath',
        default="~/.config/systemd/user",
        help='Folder where to look for service files, default: %(default)s',
    )
    show_unit.add_argument('unit', help='File/cmd/unit to show service')
    watch = subparsers.add_parser('watch')
    watch.add_argument(
        'extensions', help='Patterns of files to watch (by default inferred)', nargs='?'
    )
    watch.add_argument(
        '--exclude_patterns', help='Patterns of files to ignore (by default inferred)', nargs='+'
    )
    ls = subparsers.add_parser('ls')
    ls.add_argument(
        '--systempath',
        default="~/.config/systemd/user",
        help='Folder where to look for service files, default: %(default)s',
    )
    delete = subparsers.add_parser('delete')
    delete.add_argument(
        '--systempath',
        default="~/.config/systemd/user",
        help='Folder where to look for service files, default: %(default)s',
    )
    delete.add_argument('unit', nargs="?", help='File/cmd/unit to observe')
    return parser, parser.parse_args(args)


def choose_unit(units):
    options = []
    for unit in units:
        running = "✓" if is_unit_running(unit) or is_unit_running(unit + ".timer") else "✗"
        enabled = "✓" if is_unit_enabled(unit) else "✗"
        options.append((unit, running, enabled))

    pad = "{}|    {}    |    {}    "
    offset = max([len(x[0]) for x in options]) + 3
    formatted_options = [pad.format(x.ljust(offset), r, e) for x, r, e in options]
    quit = "-- Quit --"
    formatted_options.append(" ")
    formatted_options.append(quit)
    title = "These are known units:\n\n{}| Active  | Starts on boot".format(" " * (offset + 2))
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


def _main():
    parser, args = get_argparser()
    try:
        args.systempath = os.path.expanduser(args.systempath)
        try:
            os.makedirs(args.systempath)
        except FileExistsError:
            pass
    except AttributeError:
        pass
    if args.command == "create":
        print("Creating systemd unit...")
        service_name = install(args)
        print("Done")
        run(service_name, args.systempath)
    elif args.command == "view":
        service_name = to_sn(args.unit)
        if not os.path.exists(args.systempath + "/" + service_name + ".service"):
            print(
                "Service file does not exist. You can start by running:\n\n    sysdm create {}\n\nto create a service or run:\n\n    sysdm ls\n\nto see the services already created by sysdm.".format(
                    args.unit
                )
            )
            sys.exit(1)
        run(service_name, args.systempath)
    elif args.command == "show_unit":
        show(args)
    elif args.command == "watch":
        watch(args)
    elif args.command == "delete":
        if args.unit is None:
            units = ls(args)
            unit = choose_unit(units)
            if unit is None:
                sys.exit()
            inp = input("Are you sure you want to delete '{}'? [y/N]: ".format(unit))
            if inp.lower().strip() != "y":
                print("Aborting")
                return
        else:
            unit = args.unit
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


def main():
    try:
        _main()
    except KeyboardInterrupt:
        print("Aborted")
