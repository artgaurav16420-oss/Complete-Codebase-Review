"""Tests for ccr.fileio: newline handling and symlink refusal."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ccr.fileio import (  # noqa: E402
    _open_beneath,
    _verify_handle,
    _windows_final_path,
    write_text,
)


class TestFileioWriteText(unittest.TestCase):
    """Write semantics that the pipeline relies on."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_writes_utf8_text(self):
        path = self.dir / "note.txt"
        write_text(path, "line one\nline two\n")
        self.assertEqual(
            path.read_text(encoding="utf-8"), "line one\nline two\n"
        )

    def test_newline_parameter_is_honoured(self):
        path = self.dir / "note.txt"
        write_text(path, "a\nb\n", newline="")
        self.assertEqual(path.read_bytes(), b"a\nb\n")

    def test_refuses_to_write_through_symlink(self):
        target = self.dir / "target.txt"
        target.write_text("KEEP", encoding="utf-8")
        link = self.dir / "link.txt"
        try:
            os.symlink(target, link)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("symlink creation unavailable: " + str(exc))
        with self.assertRaises(OSError):
            write_text(link, "OVERWRITTEN")
        self.assertEqual(target.read_text(encoding="utf-8"), "KEEP")

    def test_missing_parent_is_an_error(self):
        with self.assertRaises(OSError):
            write_text(self.dir / "absent" / "note.txt", "x")

    def test_root_containment_allows_nested_write(self):
        nested = self.dir / "sub"
        nested.mkdir()
        write_text(nested / "note.txt", "ok", root=self.dir)
        self.assertEqual(
            (nested / "note.txt").read_text(encoding="utf-8"), "ok"
        )

    def test_symlinked_root_is_refused(self):
        real = self.dir / "real"
        real.mkdir()
        link = self.dir / "linkroot"
        try:
            os.symlink(real, link, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("symlink creation unavailable: " + str(exc))
        with self.assertRaises(OSError):
            write_text(link / "note.txt", "x", root=link)

    def test_symlinked_subdir_cannot_escape_root(self):
        outside = self.dir / "outside"
        outside.mkdir()
        root = self.dir / "root"
        root.mkdir()
        link = root / "sub"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("symlink creation unavailable: " + str(exc))
        with self.assertRaises(OSError):
            write_text(link / "note.txt", "x", root=root)
        self.assertEqual(list(outside.iterdir()), [])

    def test_symlinked_root_check_without_os_symlink(self):
        with mock.patch(
                "ccr.fileio.os.path.islink", side_effect=[False, True]):
            with self.assertRaises(OSError):
                write_text(self.dir / "note.txt", "x", root=self.dir)

    def test_root_on_another_drive_is_refused(self):
        with mock.patch(
                "ccr.fileio.os.path.commonpath", side_effect=ValueError):
            with self.assertRaises(OSError):
                write_text(self.dir / "note.txt", "x", root=self.dir)

    def test_parent_swap_is_detected(self):
        first = os.stat_result((0, 11, 22, 0, 0, 0, 0, 0, 0, 0))
        second = os.stat_result((0, 33, 44, 0, 0, 0, 0, 0, 0, 0))
        with mock.patch(
                "ccr.fileio.os.stat",
                side_effect=[first, second, second]):
            with self.assertRaises(OSError):
                write_text(self.dir / "note.txt", "x")

    def test_opened_descriptor_identity_is_checked(self):
        fake = os.stat_result((0, 999, 999, 0, 0, 0, 0, 0, 0, 0))
        with mock.patch("ccr.fileio.os.fstat", return_value=fake):
            with self.assertRaises(OSError):
                write_text(self.dir / "note.txt", "x")

    def test_open_beneath_walks_every_component(self):
        calls = []

        def fake_open(target, flags, mode=0o777, dir_fd=None):
            calls.append((target, dir_fd))
            return 10 + len(calls)

        root = os.path.abspath(os.sep + "root")
        rel = os.sep.join(["a", "b", "f.txt"])
        with mock.patch("ccr.fileio.os.open", side_effect=fake_open), \
                mock.patch("ccr.fileio.os.close"):
            fd = _open_beneath(root, rel, os.O_WRONLY)
        self.assertEqual(fd, 14)
        self.assertEqual(
            [call[0] for call in calls], [root, "a", "b", "f.txt"]
        )
        self.assertEqual(
            [call[1] for call in calls], [None, 11, 12, 13]
        )

    def test_open_beneath_refuses_parent_traversal(self):
        rel = os.sep.join([os.pardir, "etc", "passwd"])
        with self.assertRaises(OSError):
            _open_beneath(os.path.abspath(os.sep + "root"), rel, os.O_WRONLY)

    def test_bytes_path_and_root_are_accepted(self):
        write_text(
            os.fsencode(str(self.dir / "note.txt")), "x",
            root=os.fsencode(str(self.dir)),
        )
        self.assertEqual(
            (self.dir / "note.txt").read_text(encoding="utf-8"), "x"
        )

    @unittest.skipUnless(os.name == "posix", "POSIX openat semantics")
    def test_internal_symlink_is_refused_on_posix(self):
        root = self.dir / "root"
        other = root / "other"
        other.mkdir(parents=True)
        link = root / "sub"
        os.symlink(other, link, target_is_directory=True)
        with self.assertRaises(OSError):
            write_text(link / "note.txt", "x", root=root)

    def test_verify_handle_refuses_outside_path(self):
        outside = str(Path(self.tmp.name).parent / "outside.txt")
        with mock.patch(
                "ccr.fileio._windows_final_path", return_value=outside):
            with self.assertRaises(OSError):
                _verify_handle(str(self.dir), 1, "note.txt")

    def test_verify_handle_accepts_inside_path(self):
        final = str(self.dir / "note.txt")
        with mock.patch(
                "ccr.fileio._windows_final_path", return_value=final):
            _verify_handle(str(self.dir), 1, "note.txt")

    def test_verify_handle_skips_when_api_unavailable(self):
        with mock.patch("ccr.fileio._windows_final_path", return_value=""):
            _verify_handle(str(self.dir), 1, "note.txt")

    def _final_path(self, response):
        import types

        class FakeKernel:
            def GetFinalPathNameByHandleW(self, handle, buf, size, flags):
                if response is None:
                    return 0
                if buf is None:
                    return 100
                buf.value = response
                return 100

        fake_ctypes = types.ModuleType("ctypes")
        fake_ctypes.windll = types.SimpleNamespace(kernel32=FakeKernel())
        fake_ctypes.create_unicode_buffer = (
            lambda size: types.SimpleNamespace(value="")
        )
        fake_msvcrt = types.ModuleType("msvcrt")
        fake_msvcrt.get_osfhandle = lambda fd: 1
        with mock.patch.dict(
                sys.modules,
                {"ctypes": fake_ctypes, "msvcrt": fake_msvcrt}):
            return _windows_final_path(1)

    def test_windows_final_path_strips_verbatim_prefix(self):
        self.assertEqual(
            self._final_path("\\\\?\\C:\\root\\note.txt"),
            "C:\\root\\note.txt",
        )

    def test_windows_final_path_strips_unc_prefix(self):
        self.assertEqual(
            self._final_path("\\\\?\\UNC\\server\\share\\x"),
            "\\\\server\\share\\x",
        )

    def test_windows_final_path_reports_unavailable(self):
        self.assertEqual(self._final_path(None), "")

    def test_parent_that_is_a_symlink_after_open_is_refused(self):
        with mock.patch(
                "ccr.fileio.os.path.islink",
                side_effect=[False, False, True]):
            with self.assertRaises(OSError):
                write_text(self.dir / "note.txt", "x")


if __name__ == "__main__":
    unittest.main()
