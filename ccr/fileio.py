"""Version-compatible file helpers.

`Path.write_text(..., newline=...)` was added in Python 3.10, but this
project supports 3.9. Route explicit newline writes through `open()`.
"""

import os


def _directory_flags():
    """Flags for opening a directory without requiring read permission."""
    flags = getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    for name in ("O_PATH", "O_SEARCH"):
        value = getattr(os, name, 0)
        if value:
            return value | flags
    return os.O_RDONLY | flags


def _open_beneath(root, rel, flags):
    """Open ``root/rel`` without following a symlink below ``root``.

    ``root`` must be a resolved absolute path. Every component of ``rel`` is
    opened relative to its parent with O_NOFOLLOW, so a link swapped in below
    the validated root fails the open instead of redirecting the write.
    Ancestors of the resolved root are outside the guarantee.
    """
    if rel in (os.curdir, os.pardir) or rel.startswith(os.pardir + os.sep):
        raise OSError("refusing to write outside root: " + rel)
    root_parts = [part for part in root.split(os.sep) if part]
    rel_parts = rel.split(os.sep)
    dir_fd = os.open(os.sep, _directory_flags())
    try:
        for part in root_parts + rel_parts[:-1]:
            next_fd = os.open(part, _directory_flags(), dir_fd=dir_fd)
            os.close(dir_fd)
            dir_fd = next_fd
        return os.open(rel_parts[-1], flags, 0o666, dir_fd=dir_fd)
    finally:
        os.close(dir_fd)


def _inside(root, path):
    """Return True when path is the root or below it (case-normalised)."""
    try:
        return os.path.commonpath(
            [os.path.normcase(root), os.path.normcase(path)]
        ) == os.path.normcase(root)
    except ValueError:
        return False


def _windows_final_path(fd):
    """Return the final path of an open descriptor, or '' if unavailable.

    Resolves reparse points through the handle, so the answer reflects the
    file that was actually opened rather than the path spelling.
    """
    try:
        import ctypes
        import msvcrt
    except ImportError:
        return ""
    kernel32 = ctypes.windll.kernel32
    function = kernel32.GetFinalPathNameByHandleW
    function.argtypes = [
        ctypes.c_void_p, ctypes.c_wchar_p,
        ctypes.c_uint32, ctypes.c_uint32,
    ]
    function.restype = ctypes.c_uint32
    handle = msvcrt.get_osfhandle(fd)
    length = function(handle, None, 0, 0)
    if not length:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    written = function(handle, buffer, length + 1, 0)
    if not written:
        return ""
    path = buffer.value
    if path.startswith("\\\\?\\UNC\\"):
        path = "\\\\" + path[8:]
    elif path.startswith("\\\\?\\"):
        path = path[4:]
    return path


def _verify_handle(root, fd, path):
    """Refuse when the opened handle cannot be proven to be inside root."""
    final = _windows_final_path(fd)
    if not final:
        raise OSError(
            "refusing to write: cannot verify the opened file path: " + path
        )
    if not _inside(root, final):
        raise OSError("refusing to write outside root: " + path)


def _open_checked(path, flags, root=None):
    """Open a file with path-level checks (no POSIX dir_fd walk).

    Records the parent identity before the open and compares it after,
    re-checks that neither the leaf nor the parent is now a symlink, and
    verifies that the descriptor names the file the path currently names.
    On Windows, the handle's final path is also checked against ``root``.
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
        if root is not None:
            _verify_handle(root, fd, path)
    except BaseException:
        os.close(fd)
        raise
    return fd


def write_text(path, text, newline="\n", root=None):
    """Write UTF-8 text with explicit newline handling on Python 3.9+.

    Refuses to follow a symlink at the destination. When ``root`` is given,
    the destination must resolve inside it; on POSIX every component below the
    resolved root is opened with O_NOFOLLOW, so a link that resolves outside is
    refused. A link that resolves inside the root is written through its target.
    On Windows the opened handle's final path is checked against the root.
    """
    path = os.fsdecode(os.fspath(path))
    if os.path.islink(path):
        raise OSError("refusing to write through symlink: " + path)
    root_real = None
    root_abs = None
    rel = None
    if root is not None:
        root = os.fsdecode(os.fspath(root))
        if os.path.islink(root):
            raise OSError("refusing to write under symlinked root: " + root)
        root_real = os.path.realpath(root)
        root_abs = os.path.abspath(root_real)
        try:
            if os.path.commonpath(
                    [root_abs, os.path.realpath(path)]
            ) != root_abs:
                raise OSError("refusing to write outside root: " + path)
            rel = os.path.relpath(os.path.realpath(path), root_abs)
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
        if not hasattr(os, "O_NOFOLLOW"):
            raise OSError(
                "platform lacks O_NOFOLLOW; refusing rooted write: " + path
            )
        fd = _open_beneath(root_abs, rel, flags)
    else:
        fd = _open_checked(path, flags, root=root_abs)
    try:
        os.ftruncate(fd, 0)
    except BaseException:
        os.close(fd)
        raise
    with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as handle:
        handle.write(text)
