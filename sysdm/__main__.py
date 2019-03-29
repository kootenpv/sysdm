import sys
from sysdm.sysctl import install, show, ls
from sysdm.file_watcher import watch
from sysdm.utils import get_output, is_unit_running
from sysdm.runner import run
from pick import pick


def get_argparser(args=None):
    """ This is the function that is run from commandline with `chist` """
    import argparse

    parser = argparse.ArgumentParser(description='sysdm')
    subparsers = parser.add_subparsers(dest="command")
    create = subparsers.add_parser('create')
    create.add_argument(
        '--systempath', default="/etc/systemd/system", help='Folder to save the service file'
    )
    create.add_argument(
        '--norestart', action='store_true', help='Whether to prevent auto restart on error'
    )
    create.add_argument('fname', help='File to run (and name of unit file)')
    create.add_argument('extra_args', help='File to run (and name of unit file)', nargs="*")
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
        '--systempath', default="/etc/systemd/system", help='Folder to save the service file'
    )
    view.add_argument('fname', help='File to observe (and name of unit file)')
    show_unit = subparsers.add_parser('show_unit')
    show_unit.add_argument(
        '--systempath', default="/etc/systemd/system", help='Folder to save the service file'
    )
    show_unit.add_argument('fname', help='File to show service from (and name of unit file)')
    watch = subparsers.add_parser('watch')
    watch.add_argument(
        'extensions', help='Patterns of files to watch (by default inferred)', nargs='+'
    )
    watch.add_argument(
        '--exclude_patterns', help='Patterns of files to ignore (by default inferred)', nargs='+'
    )
    ls = subparsers.add_parser('ls')
    ls.add_argument(
        '--systempath', default="/etc/systemd/system", help='Folder to save the service file'
    )
    return parser.parse_args(args)


def main():
    args = get_argparser()
    if args.command == "create":
        print("Creating systemd unit...")
        install(args)
        show(args)
    elif args.command == "view":
        service_name = args.fname.replace(".", "_")
        cmd = f"systemctl is-enabled {args.fname.replace('.', '_')} || echo 'broken'"
        is_broken = get_output(cmd) == "broken"
        if is_broken:
            print(f"First start by running 'sudo sysdm create {args.fname}'")
            sys.exit(0)
        run(service_name)
    elif args.command == "show_unit":
        show(args)
    elif args.command == "watch":
        watch(args)
    elif args.command == "ls":
        units = ls(args)
        if units:
            formatted_options = []
            for unit in units:
                is_running = is_unit_running(unit)
                status = "✓" if is_running else "✗"
                formatted_options.append(f"{status} {unit}")
            quit = "-- Quit --"
            formatted_options.append(quit)
            chosen, index = pick(formatted_options, "These are known units:")
            if chosen == quit:
                return
            run(units[index])
        else:
            print("sysdm knows of no units. Why don't you make one? `sudo sysdm create myfile.py`")

    else:
        raise ValueError("No command given")
