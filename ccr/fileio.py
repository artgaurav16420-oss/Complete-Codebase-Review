"""Version-compatible file helpers.

`Path.write_text(..., newline=...)` was added in Python 3.10, but this
project supports 3.9. Route explicit newline writes through `open()`.
"""

import os


def _open_beneath(path, root, flags):
    """Open ``path`` under ``root`` without following any symlink component.

    Every directory from ``root`` down is opened relative to its parent with
    O_NOFOLLOW, so a link swapped in at any level fails the open instead of
    redirecting the write.
    """
    try:
        rel = os.path.relpath(path, root)
    except ValueError:
        raise OSError("refusing to write outside root: " + path)
    if rel in (os.curdir, os.pardir) or rel.startswith(os.pardir + os.sep):
        raise OSError("refusing to write outside root: " + path)
    parts = rel.split(os.sep)
    dir_fd = os.open(
        root,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        for part in parts[:-1]:
            next_fd = os.open(
                part,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=dir_fd,
            )
            os.close(dir_fd)
            dir_fd = next_fd
        return os.open(parts[-1], flags, 0o666, dir_fd=dir_fd)
    finally:
        os.close(dir_fd)


def _open_checked(path, flags):
    """Open a file with path-level checks (no POSIX dir_fd walk).

    Records the parent identity before the open and compares it after, and
    verifies that the descriptor names the file the path currently names.
    """
    parent = os.path.dirname(os.path.abspath(path)) or "."
    try:
        before = os.stat(parent)
    except OSError:
        before = None
    fd = os.open(path, flags, 0o666)
    try:
        if os.path.islink(parent):
            raise OSError(
                "refusing to write: parent is a symlink: " + parent
            )
        after = os.stat(parent)
        if before is not None and (
                (before.st_dev, before.st_ino)
                != (after.st_dev, after.st_ino)):
            raise OSError(
                "refusing to write: parent directory changed during open: "
                + parent
            )
        opened = os.fstat(fd)
        current = os.stat(path)
        if (opened.st_dev, opened.st_ino) != (
                current.st_dev, current.st_ino):
            raise OSError(
                "refusing to write: opened file is not the named file: "
                + path
            )
    except BaseException:
        os.close(fd)
        raise
    return fd


def write_text(path, text, newline="\n", root=None):
    """Write UTF-8 text with explicit newline handling on Python 3.9+.

    Refuses to follow a symlink at the destination. When ``root`` is given,
    the destination must resolve inside it; on POSIX every component is opened
    with O_NOFOLLOW, so no symlink below the root is followed. On Windows the
    leaf and parent checks are best effort and an internal link that stays
    inside the root may be followed.
    """
    path = os.fspath(path)
    if os.path.islink(path):
        raise OSError("refusing to write through symlink: " + path)
    if root is not None:
        root = os.fspath(root)
        if os.path.islink(root):
            raise OSError("refusing to write under symlinked root: " + root)
        root_real = os.path.realpath(root)
        try:
            inside = os.path.commonpath(
                [root_real, os.path.realpath(path)]
            ) == root_real
        except ValueError:
            inside = False
        if not inside:
            raise OSError("refusing to write outside root: " + path)
    # O_NOFOLLOW closes the leaf race on POSIX. Windows has no equivalent
    # flag, so _open_checked verifies the descriptor identity instead.
    flags = os.O_WRONLY | os.O_CREAT
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    if root is not None and os.name == "posix":
        fd = _open_beneath(os.path.abspath(path), os.path.abspath(root), flags)
    else:
        fd = _open_checked(path, flags)
    try:
        os.ftruncate(fd, 0)
    except BaseException:
        os.close(fd)
        raise
    with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as handle:
        handle.write(text)
