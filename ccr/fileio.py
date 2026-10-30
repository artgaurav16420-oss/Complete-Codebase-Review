"""Version-compatible file helpers.

`Path.write_text(..., newline=...)` was added in Python 3.10, but this
project supports 3.9. Route explicit newline writes through `open()`.
"""

import os


def _open_beneath(root, rel, flags):
    """Open ``root/rel`` without following any symlink component.

    ``root`` must be a resolved absolute path. The walk starts at the
    filesystem root so swapping an ancestor cannot redirect it: every
    directory is opened relative to its parent with O_NOFOLLOW.
    """
    if rel in (os.curdir, os.pardir) or rel.startswith(os.pardir + os.sep):
        raise OSError("refusing to write outside root: " + rel)
    root_parts = [part for part in root.split(os.sep) if part]
    rel_parts = rel.split(os.sep)
    dir_fd = os.open(os.sep, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        for part in root_parts + rel_parts[:-1]:
            next_fd = os.open(
                part,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=dir_fd,
            )
            os.close(dir_fd)
            dir_fd = next_fd
        return os.open(rel_parts[-1], flags, 0o666, dir_fd=dir_fd)
    finally:
        os.close(dir_fd)


def _open_checked(path, flags):
    """Open a file with path-level checks (no POSIX dir_fd walk).

    Records the parent identity before the open and compares it after,
    re-checks that neither the leaf nor the parent is now a symlink, and
    verifies that the descriptor names the file the path currently names.
    """
    parent = os.path.dirname(os.path.abspath(path)) or "."
    try:
        before = os.stat(parent)
    except OSError:
        before = None
    fd = os.open(path, flags, 0o666)
    try:
        if os.path.islink(path):
            raise OSError("refusing to write through symlink: " + path)
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
    the destination must resolve inside it; on POSIX every component from the
    filesystem root down is opened with O_NOFOLLOW, so no symlink is followed.
    On Windows the leaf and parent checks are best effort.
    """
    path = os.fsdecode(os.fspath(path))
    if os.path.islink(path):
        raise OSError("refusing to write through symlink: " + path)
    root_real = None
    rel = None
    if root is not None:
        root = os.fsdecode(os.fspath(root))
        if os.path.islink(root):
            raise OSError("refusing to write under symlinked root: " + root)
        root_real = os.path.realpath(root)
        root_real_abs = os.path.abspath(root_real)
        try:
            if os.path.commonpath(
                    [root_real_abs, os.path.realpath(path)]
            ) != root_real_abs:
                raise OSError("refusing to write outside root: " + path)
            rel = os.path.relpath(os.path.abspath(path), os.path.abspath(root))
        except ValueError:
            raise OSError("refusing to write outside root: " + path)
        if rel == os.pardir or rel.startswith(os.pardir + os.sep):
            raise OSError("refusing to write outside root: " + path)
    # O_NOFOLLOW closes the leaf race on POSIX. Windows has no equivalent
    # flag, so _open_checked verifies the descriptor identity instead.
    flags = os.O_WRONLY | os.O_CREAT
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    if root_real is not None and os.name == "posix":
        fd = _open_beneath(root_real_abs, rel, flags)
    else:
        fd = _open_checked(path, flags)
    try:
        os.ftruncate(fd, 0)
    except BaseException:
        os.close(fd)
        raise
    with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as handle:
        handle.write(text)
