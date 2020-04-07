import os
import sys
import inotify.constants
import inotify.adapters
from sysdm.utils import is_git_ignored


def watch(args):
    current_dir = os.path.abspath(".")
    if not args.extensions:
        print("WARNING: Not watching '{}' for changes (nothing to follow)".format(current_dir))
        return
    i = inotify.adapters.Inotify()

    i.add_watch(current_dir, mask=inotify.constants.IN_CLOSE_WRITE)

    extensions = [args.extensions] if isinstance(args.extensions, str) else args.extensions

    print("Watching directory '{}' for changes in '{}'".format(current_dir, extensions))
    for event in i.event_gen(yield_nones=False):
        (_, _, path, filename) = event
        if any([x in filename for x in args.exclude_patterns]):
            continue
        if os.path.exists(".git") and is_git_ignored(os.path.join(path, filename)):
            print("File '{}' changed but ignored by gitignore".format(filename))
            continue
        if any([filename.endswith(x) for x in extensions]):
            import pdb

            pdb.set_trace()
            print(
                "File '{filename}' changed in '{path}', restarting service".format(
                    filename=filename, path=path
                )
            )
            sys.exit(0)
