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


COVERAGE_PIN = re.compile(r"coverage==")


def workflow_job(text, name):
    """Return the text of one top-level job in a workflow file.

    Job keys sit at two-space indent under ``jobs:``; every key inside a job
    is deeper, so the next two-space key ends the block.
    """
    lines = text.splitlines(True)
    start = lines.index("  " + name + ":\n")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.startswith("  ") and not line.startswith("   "):
            if line.rstrip().endswith(":"):
                end = index
                break
    return "".join(lines[start:end])


class TestReleaseCoveragePin(unittest.TestCase):
    """The release matrix runs 3.9, so an exact coverage pin must be split.

    coverage 7.14 and later require Python 3.10; an unscoped pin fails to
    install on the 3.9 leg and blocks every tag release before any test runs.
    """

    def test_matrix_coverage_pin_is_scoped_to_an_interpreter(self):
        text = (ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
        job = workflow_job(text, "matrix-test")
        pins = [line for line in job.splitlines() if COVERAGE_PIN.search(line)]
        self.assertTrue(pins)
        for line in pins:
            with self.subTest(line=line.strip()):
                self.assertIn("python_version", line)


if __name__ == "__main__":
    unittest.main()
