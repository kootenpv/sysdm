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
EXCLUDED_DIR_SET = frozenset(EXCLUDED_DIRS)

# Recursively watching one of these means watching effectively the whole machine.
# It is always a misconfiguration (usually a unit generated with the wrong
# WorkingDirectory) and costs a full tree walk plus an inotify watch per directory.
UNWATCHABLE_ROOTS = frozenset(
    [os.path.expanduser("~"), "/", "/home", "/tmp", "/var", "/etc", "/usr"]
)

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


def _build_watcher(root):
    """Create an Inotify watching `root` recursively, pruning excluded and
    unreadable directories *during* the walk.

    InotifyTree() is deliberately not used: it descends into every directory
    (node_modules, .git, .venv and friends included) before any filtering can
    happen, and a single unreadable directory makes its constructor raise
    PermissionError. Pruning here keeps both the walk and the kernel-side watch
    table proportional to the code actually being watched.
    """
    i = inotify.adapters.Inotify(block_duration_s=1)
    watched = 0
    skipped = 0
    for dirpath, dirnames, _ in os.walk(root, topdown=True, onerror=None):
        # topdown=True: mutating dirnames in place prunes the walk itself.
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIR_SET]
        try:
            i.add_watch(dirpath, WATCH_MASK)
            watched += 1
        except (OSError, inotify.calls.InotifyError):
            # Unreadable, vanished mid-walk, or watch limit hit; skip this subtree
            # rather than taking down the whole watcher.
            dirnames[:] = []
            skipped += 1
    msg = "Watching {n} directories under '{root}'".format(n=watched, root=root)
    if skipped:
        msg += " ({s} skipped as unreadable)".format(s=skipped)
    print(msg)
    return i


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

    # An extension containing a path separator can never match a bare filename,
    # so the watcher would run forever without ever firing. This shows up when a
    # generator passes the ExecStart binary path into the extensions slot.
    bad = [x for x in extensions if "/" in x]
    if bad:
        print(
            "ERROR: not an extension: {}. Expected suffixes like '.py', "
            "not paths; refusing to watch.".format(", ".join(repr(b) for b in bad))
        )
        return

    if current_dir.rstrip("/") in UNWATCHABLE_ROOTS or current_dir == "/":
        print(
            "ERROR: refusing to recursively watch '{}'. This is almost certainly a "
            "wrong WorkingDirectory in the unit file.".format(current_dir)
        )
        return

    exclude_patterns = list(exclude_patterns or [])
    exclude_patterns.append("flycheck")

    print("Watching '{}' (recursive) for changes in '{}'".format(current_dir, extensions))

    tree = _build_watcher(current_dir)
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
        except (inotify.calls.InotifyError, OSError) as e:
            # OSError covers PermissionError from a directory that became
            # unreadable, which is not an InotifyError and previously escaped
            # this handler and killed the process.
            offending = _extract_offending_path()
            if _should_exclude_path(offending):
                continue
            print("Inotify error on '{}': {} - reinitializing watcher".format(offending, e))
            while not os.path.exists(current_dir):
                time.sleep(0.1)
            tree = _build_watcher(current_dir)
            started_at = time.monotonic()
            time.sleep(0.1)
        except KeyboardInterrupt:
            return
        except Exception:
            print(traceback.format_exc())
            return
