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

from ccr.fileio import write_text  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
