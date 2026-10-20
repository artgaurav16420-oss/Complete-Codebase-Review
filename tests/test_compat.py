"""Python 3.9 compatibility guards.

CI runs 3.9-3.13. A 3.10-only API slipped through once
(`Path.write_text(newline=...)`), so the production tree is scanned.
"""

import re
import tempfile
import unittest
from pathlib import Path

from ccr.fileio import write_text

ROOT = Path(__file__).resolve().parent.parent
PRODUCTION = [ROOT / "install.py", ROOT / "tools" / "generate.py"]
PRODUCTION.extend(sorted((ROOT / "ccr").glob("*.py")))

WRITE_NEWLINE = re.compile(
    r"\.write_text\((?:[^()]|\([^()]*\))*?newline\s*=", re.DOTALL
)
BANNED = [
    "itertools.pairwise",
    "bit_count(",
    "import tomllib",
    "datetime.UTC",
]


class TestWriteTextHelper(unittest.TestCase):
    """The helper writes exact bytes on every supported version."""

    def test_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.txt"
            write_text(path, "a\nb\n")
            self.assertEqual(path.read_bytes(), b"a\nb\n")

    def test_crlf(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.txt"
            write_text(path, "a\nb\n", newline="\r\n")
            self.assertEqual(path.read_bytes(), b"a\r\nb\r\n")


class TestNo310Apis(unittest.TestCase):
    """Production code must run on Python 3.9."""

    def _text(self, path):
        return path.read_text(encoding="utf-8")

    def test_no_write_text_newline(self):
        for path in PRODUCTION:
            if path.name == "fileio.py":
                continue
            with self.subTest(path=str(path)):
                match = WRITE_NEWLINE.search(self._text(path))
                self.assertIsNone(
                    match,
                    "Path.write_text(newline=) is 3.10+; use ccr.fileio.write_text",
                )

    def test_no_310_stdlib_apis(self):
        for path in PRODUCTION:
            text = self._text(path)
            for needle in BANNED:
                with self.subTest(path=str(path), api=needle):
                    self.assertNotIn(needle, text)


if __name__ == "__main__":
    unittest.main()
