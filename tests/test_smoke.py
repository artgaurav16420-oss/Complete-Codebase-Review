"""Smoke tests for install.py — CLI checks.

Runs install.py entry point with various flags and asserts exit codes/output.
Uses in-process calls with patched sys.argv for coverage tracking.
"""
import io
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


def _import_install():
    """Import install module for in-process testing."""
    p = str(Path(__file__).resolve().parent.parent)
    if p not in sys.path:
        sys.path.insert(0, p)
    import install as install_mod
    return install_mod


INSTALL_PY = str(Path(__file__).resolve().parent.parent / "install.py")


class TestChecksumVerification(unittest.TestCase):
    """Tests for --checksum and --self-verify flags using in-process calls."""

    @classmethod
    def setUpClass(cls):
        cls.install = _import_install()

    def _write_script_and_checksum(self, tmpdir, content=b"fake script", valid_hash=None):
        """Write a fake script and optional .sha256 file. Returns (script_path, hash)."""
        script = Path(tmpdir) / "install.py"
        script.write_bytes(content)
        if valid_hash is None:
            valid_hash = self.install._compute_sha256(script)
        return script, valid_hash

    def test_self_verify_passes(self):
        """Verify --self-verify succeeds with valid checksum."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            script, valid_hash = self._write_script_and_checksum(tmpdir)
            checksum_file = script.parent / "install.py.sha256"
            checksum_file.write_text(valid_hash + "  install.py\n", encoding="utf-8")
            with patch.object(self.install, "__file__", str(script)), \
                 patch("sys.argv", [str(script), "--self-verify"]), \
                 patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                with self.assertRaises(SystemExit) as ctx:
                    self.install.main()
                self.assertEqual(ctx.exception.code, 0)
                self.assertIn("Checksum verification passed", mock_stdout.getvalue())

    def test_self_verify_with_empty_checksum_file_fails(self):
        """Verify --self-verify fails with empty checksum file."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            script, _ = self._write_script_and_checksum(tmpdir)
            checksum_file = script.parent / "install.py.sha256"
            checksum_file.write_text("   \n", encoding="utf-8")
            with patch.object(self.install, "__file__", str(script)), \
                 patch("sys.argv", [str(script), "--self-verify"]), \
                 patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                with self.assertRaises(SystemExit) as ctx:
                    self.install.main()
                self.assertEqual(ctx.exception.code, 1)
                self.assertIn("empty", mock_stdout.getvalue().lower())

    def test_self_verify_with_invalid_checksum_format_fails(self):
        """Verify --self-verify fails with non-hex content."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            script, _ = self._write_script_and_checksum(tmpdir)
            checksum_file = script.parent / "install.py.sha256"
            checksum_file.write_text("not-a-hex-string\n", encoding="utf-8")
            with patch.object(self.install, "__file__", str(script)), \
                 patch("sys.argv", [str(script), "--self-verify"]), \
                 patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                with self.assertRaises(SystemExit) as ctx:
                    self.install.main()
                self.assertEqual(ctx.exception.code, 1)
                self.assertIn("invalid checksum format", mock_stdout.getvalue().lower())

    def test_self_verify_with_missing_checksum_file_fails(self):
        """Verify --self-verify fails when checksum file is missing."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            script, _ = self._write_script_and_checksum(tmpdir)
            with patch.object(self.install, "__file__", str(script)), \
                 patch("sys.argv", [str(script), "--self-verify"]), \
                 patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                with self.assertRaises(SystemExit) as ctx:
                    self.install.main()
                self.assertEqual(ctx.exception.code, 1)
                self.assertIn("install.py.sha256 not found", mock_stdout.getvalue())

    def test_self_verify_with_wrong_hash_fails(self):
        """Verify --self-verify fails when checksum mismatches."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            script, _ = self._write_script_and_checksum(tmpdir)
            checksum_file = script.parent / "install.py.sha256"
            checksum_file.write_text("0" * 64 + "  install.py\n", encoding="utf-8")
            with patch.object(self.install, "__file__", str(script)), \
                 patch("sys.argv", [str(script), "--self-verify"]), \
                 patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                with self.assertRaises(SystemExit) as ctx:
                    self.install.main()
                self.assertEqual(ctx.exception.code, 1)
                self.assertIn("FAILED", mock_stdout.getvalue())

    def test_checksum_flag_passes(self):
        """Verify --checksum succeeds with valid hash."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            script, valid_hash = self._write_script_and_checksum(tmpdir)
            with patch.object(self.install, "__file__", str(script)), \
                 patch("sys.argv", ["install.py", "--checksum", valid_hash]), \
                 patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                with self.assertRaises(SystemExit) as ctx:
                    self.install.main()
                self.assertEqual(ctx.exception.code, 0)
                self.assertIn("Checksum verification passed", mock_stdout.getvalue())

    def test_checksum_flag_fails_with_invalid_hash(self):
        """Verify --checksum fails with incorrect hash."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            script, _ = self._write_script_and_checksum(tmpdir)
            with patch.object(self.install, "__file__", str(script)), \
                 patch("sys.argv", ["install.py", "--checksum", "0" * 64]), \
                 patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                with self.assertRaises(SystemExit) as ctx:
                    self.install.main()
                self.assertEqual(ctx.exception.code, 1)
                self.assertIn("FAILED", mock_stdout.getvalue())

    def test_checksum_flag_fails_with_bad_format(self):
        """Verify --checksum rejects non-hex or wrong-length input."""
        import tempfile
        bad_inputs = ["short", "xyz" * 30]
        for bad in bad_inputs:
            with self.subTest(input=bad):
                with tempfile.TemporaryDirectory() as tmpdir:
                    script, _ = self._write_script_and_checksum(tmpdir)
                    with patch.object(self.install, "__file__", str(script)), \
                         patch("sys.argv", ["install.py", "--checksum", bad]), \
                         patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                        with self.assertRaises(SystemExit) as ctx:
                            self.install.main()
                        self.assertEqual(ctx.exception.code, 1)
                        self.assertIn("Invalid checksum format", mock_stdout.getvalue())

    def test_help_shows_checksum_options(self):
        """Verify --help mentions checksum flags."""
        with patch("sys.argv", ["install.py", "--help"]), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            with self.assertRaises(SystemExit) as ctx:
                self.install.main()
            self.assertEqual(ctx.exception.code, 0)
            output = mock_stdout.getvalue()
            self.assertIn("--checksum", output)
            self.assertIn("--self-verify", output)


class TestNoColorEnv(unittest.TestCase):
    """Tests for NO_COLOR env var suppressing ANSI codes in the checksum path."""

    @classmethod
    def setUpClass(cls):
        cls.install = _import_install()

    def _no_color_env(self):
        env = os.environ.copy()
        env["NO_COLOR"] = "1"
        return env

    def test_no_color_suppresses_ansi(self):
        """Verify NO_COLOR suppresses ANSI escape codes."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "install.py"
            script.write_text("")
            valid_hash = self.install._compute_sha256(script)
            checksum_file = script.parent / "install.py.sha256"
            checksum_file.write_text(valid_hash + "  install.py\n", encoding="utf-8")
            with patch.object(self.install, "__file__", str(script)), \
                 patch("sys.argv", [str(script), "--self-verify"]), \
                 patch("sys.stdout", new_callable=io.StringIO) as mock_stdout, \
                 patch.dict(os.environ, {"NO_COLOR": "1"}, clear=True):
                with self.assertRaises(SystemExit):
                    self.install.main()
                output = mock_stdout.getvalue()
                self.assertNotIn("\033[", output)

    def test_no_color_still_outputs_text(self):
        """Verify NO_COLOR still outputs text without ANSI codes."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "install.py"
            script.write_text("")
            valid_hash = self.install._compute_sha256(script)
            checksum_file = script.parent / "install.py.sha256"
            checksum_file.write_text(valid_hash + "  install.py\n", encoding="utf-8")
            with patch.object(self.install, "__file__", str(script)), \
                 patch("sys.argv", [str(script), "--self-verify"]), \
                 patch("sys.stdout", new_callable=io.StringIO) as mock_stdout, \
                 patch.dict(os.environ, {"NO_COLOR": "1"}, clear=True):
                with self.assertRaises(SystemExit):
                    self.install.main()
                output = mock_stdout.getvalue()
                self.assertIn("Checksum verification passed", output)


if __name__ == "__main__":
    unittest.main()
