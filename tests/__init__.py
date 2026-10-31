# Complete Codebase Review — test suite.
# Test discovery is handled by unittest.TestCase; this file
# enables `python -m unittest discover -s tests` to work.

import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _reject_cmd_metacharacters(path):
    """Refuse a path that cmd.exe would re-parse inside the junction call."""
    for char in ('"', "&", "|", "<", ">", "^", "%"):
        if char in path:
            raise OSError(
                "cannot link a path containing {!r}: {}".format(char, path)
            )


def create_directory_link(link, target):
    """Link ``link`` to the ``target`` directory.

    On Windows a junction (``mklink /J``) is tried first because
    ``os.symlink`` needs Developer Mode or the symlink privilege, with
    ``os.symlink`` as the fallback. On POSIX ``os.symlink`` is the only
    mechanism. Raises OSError when no mechanism works.
    """
    link, target = str(link), str(target)
    _reject_cmd_metacharacters(link)
    _reject_cmd_metacharacters(target)
    junction_error = None
    if sys.platform == "win32":
        # A separate argv element per argument lets list2cmdline quote spaces
        # correctly; cmd.exe still re-parses the line, so characters it
        # treats specially are rejected above.
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", link, target],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return
        junction_error = result.stderr.strip() or result.stdout.strip()
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        raise OSError(junction_error or str(exc)) from exc
