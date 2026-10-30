"""Version-compatible file helpers.

`Path.write_text(..., newline=...)` was added in Python 3.10, but this
project supports 3.9. Route explicit newline writes through `open()`.
"""

import os


def write_text(path, text, newline="\n"):
    """Write UTF-8 text with explicit newline handling on Python 3.9+.

    Refuses to follow a symlink at the destination. The review cache lives
    inside the repository under review, so a link planted there must not
    redirect a write to a file outside it.
    """
    path = os.fspath(path)
    if os.path.islink(path):
        raise OSError("refusing to write through symlink: " + path)
    # O_NOFOLLOW closes the race on POSIX. Windows has no equivalent flag, so
    # the islink pre-check is best effort there.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o666)
    with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as handle:
        handle.write(text)
