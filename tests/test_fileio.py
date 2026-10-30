"""Tests for ccr.fileio: newline handling and symlink refusal."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
