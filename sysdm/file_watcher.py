import os
import sys
import inotify.constants
import inotify.adapters


def watch(args):
    i = inotify.adapters.Inotify()

    current_dir = os.path.abspath(".")
    i.add_watch(current_dir, mask=inotify.constants.IN_CLOSE_WRITE)

    print("Watching directory {} for changes in {}".format(current_dir, args.extensions))
    for event in i.event_gen(yield_nones=False):
        (_, _, path, filename) = event
        if any([x in filename for x in args.exclude_patterns]):
            continue
        if any([filename.endswith(x) for x in args.extensions]):
            print(
                "File {filename} changed in {path}, restarting service".format(
                    filename=filename, path=path
                )
            )
            sys.exit(0)
