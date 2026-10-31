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


def create_directory_link(link, target):
    """Link ``link`` to the ``target`` directory.

    On Windows a junction (``mklink /J``) is tried first because
    ``os.symlink`` needs Developer Mode or the symlink privilege; every
    other platform starts with ``os.symlink``. Each mechanism falls back to
    the other. Raises OSError when neither works.
    """
    link, target = str(link), str(target)
    if '"' in link or '"' in target:
        raise OSError(
            "cannot link a path containing a double quote: "
            "{} -> {}".format(link, target)
        )
    junction_error = None
    if sys.platform == "win32":
        # cmd.exe re-parses its command line, so both paths are quoted; a
        # double quote inside a path cannot be escaped and is rejected above.
        command = 'mklink /J "{}" "{}"'.format(link, target)
        result = subprocess.run(
            ["cmd", "/c", command], capture_output=True, text=True
        )
        if result.returncode == 0:
            return
        junction_error = result.stderr.strip() or result.stdout.strip()
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        raise OSError(junction_error or str(exc)) from exc
