import os
import sys
import time
import traceback
import inotify.constants
import inotify.adapters
import inotify.calls
from sysdm.utils import is_git_ignored


EXCLUDED_DIRS = [
    "target", "__pycache__", ".pytest_cache", ".mypy_cache",
    "node_modules", ".git", ".venv", "venv", ".tox", "dist", "build",
]

WATCH_MASK = (
    inotify.constants.IN_CLOSE_WRITE  # Direct writes (vim, nano)
    | inotify.constants.IN_MOVED_TO   # Atomic-rename saves (VSCode, JetBrains, Claude Code)
    | inotify.constants.IN_CREATE     # File creation (git checkout)
)

# After (re)starting, ignore matching events for this long. A freshly restarted
# watcher would otherwise immediately re-exit if the filesystem is still churning
# (e.g. midnight snapshots/maintenance), turning a single burst into a restart storm
# that propagates through PartOf= and trips the service's StartLimit.
STARTUP_GRACE_S = 1.0


def _should_exclude_path(path):
    return any(
        "/{d}/".format(d=d) in path or path.endswith("/" + d)
        for d in EXCLUDED_DIRS
    )


def _extract_offending_path():
    tb = sys.exc_info()[2]
    while tb is not None:
        if "full_path" in tb.tb_frame.f_locals:
            return tb.tb_frame.f_locals["full_path"]
        tb = tb.tb_next
    return "unknown"


def watch(extensions, exclude_patterns):
    current_dir = os.path.abspath(".")
    if not extensions:
        print("WARNING: Not watching '{}' for changes (nothing to follow)".format(current_dir))
        return

    extensions = [extensions] if isinstance(extensions, str) else extensions
    exclude_patterns = list(exclude_patterns or [])
    exclude_patterns.append("flycheck")

    print("Watching directory '{}' (recursive) for changes in '{}'".format(current_dir, extensions))

    tree = inotify.adapters.InotifyTree(current_dir, mask=WATCH_MASK, block_duration_s=1)
    started_at = time.monotonic()

    while True:
        try:
            for event in tree.event_gen(yield_nones=False):
                (_, _, path, filename) = event
                if _should_exclude_path(path):
                    continue
                if any(x in filename for x in exclude_patterns):
                    continue
                full_filename = os.path.join(path, filename)
                if os.path.exists(".git") and is_git_ignored(full_filename):
                    print("File '{}' changed but ignored by gitignore".format(filename))
                    continue
                # :-7 is for rsync using a postfix for the file (e.g. '.ss.py.vFiJcy')
                if any(filename.endswith(x) or (filename.startswith(".") and filename[:-7].endswith(x)) for x in extensions):
                    if time.monotonic() - started_at < STARTUP_GRACE_S:
                        print("File '{filename}' changed in '{path}' during startup grace, ignoring".format(filename=filename, path=path))
                        continue
                    print("File '{filename}' changed in '{path}', restarting service".format(filename=filename, path=path))
                    sys.exit(0)
        except inotify.calls.InotifyError as e:
            offending = _extract_offending_path()
            if _should_exclude_path(offending):
                continue
            print("Inotify error on '{}': {} - reinitializing watcher".format(offending, e))
            if not os.path.exists(current_dir):
                while not os.path.exists(current_dir):
                    time.sleep(0.1)
            tree = inotify.adapters.InotifyTree(current_dir, mask=WATCH_MASK, block_duration_s=1)
            started_at = time.monotonic()
            time.sleep(0.1)
        except KeyboardInterrupt:
            return
        except Exception:
            print(traceback.format_exc())
            return
