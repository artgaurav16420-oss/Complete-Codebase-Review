"""Tests for tools.coverage_floor."""

import contextlib
import io
import json
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.coverage_floor import check, main

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools" / "coverage_floor.py"


def entry(percent):
    return {"summary": {"percent_covered": percent}}


class TestCoverageFloor(unittest.TestCase):
    def test_empty_report_fails(self):
        self.assertTrue(check({}))

    def test_pytools_is_not_excluded(self):
        failures = check({"files": {"pytools/x.py": entry(0.0)}})
        self.assertEqual(len(failures), 1)

    def test_tools_directory_is_excluded(self):
        report = {"files": {
            "tools/x.py": entry(0.0), "src/a.py": entry(90.0),
        }}
        self.assertEqual(check(report), [])

    def test_windows_tools_path_is_excluded(self):
        report = {"files": {
            "tools\\generate.py": entry(0.0), "src/a.py": entry(90.0),
        }}
        self.assertEqual(check(report), [])

    def test_all_files_skipped_fails(self):
        self.assertTrue(check({"files": {"tools/x.py": entry(0.0)}}))

    def test_mytests_is_not_excluded(self):
        self.assertEqual(len(check({"files": {"mytests/x.py": entry(0.0)}})), 1)

    def test_missing_summary_fails(self):
        self.assertTrue(check({"files": {"src/a.py": {}}}))

    def test_pass_and_fail(self):
        report = {"files": {"src/a.py": entry(90.0), "src/b.py": entry(70.0)}}
        self.assertEqual(check(report), [("src/b.py", 70.0)])


class TestCoverageFloorMain(unittest.TestCase):
    """main() is the CI gate: its return value is the step's exit code."""

    def _write_report(self, directory, payload):
        path = Path(directory) / "coverage.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return str(path)

    def _run_main(self, argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(argv)
        return code, buffer.getvalue()

    def _run_script(self, path, *extra):
        return subprocess.run(
            [sys.executable, str(SCRIPT), path] + list(extra),
            capture_output=True, text=True,
        )

    def test_all_modules_above_floor_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_report(tmp, {"files": {
                "ccr/a.py": entry(95.0), "install.py": entry(85.0),
            }})
            code, output = self._run_main(["coverage_floor.py", path])
        self.assertEqual(code, 0)
        self.assertIn("[SUCCESS] all modules >= 80.0%", output)

    def test_module_below_floor_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_report(tmp, {"files": {
                "ccr/a.py": entry(95.0), "ccr/b.py": entry(70.0),
            }})
            code, output = self._run_main(["coverage_floor.py", path])
        self.assertEqual(code, 1)
        self.assertIn("[FAIL] ccr/b.py: 70.0% < 80.0%", output)
        self.assertIn("[FAIL] 1 module(s) below the per-file floor", output)

    def test_nan_percent_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_report(tmp, {"files": {
                "ccr/a.py": entry(float("nan")),
            }})
            with open(path, encoding="utf-8") as handle:
                # json.dump emits the non-standard NaN token by default.
                self.assertIn("NaN", handle.read())
            code, output = self._run_main(["coverage_floor.py", path])
        self.assertEqual(code, 1)
        self.assertIn("[FAIL] ccr/a.py: 0.0% < 80.0%", output)

    def test_huge_integer_percent_fails_instead_of_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_report(tmp, {"files": {
                "ccr/a.py": entry(10 ** 400),
            }})
            result = self._run_script(path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("[FAIL] ccr/a.py: 0.0% < 80.0%", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_floor_argument_overrides_the_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_report(tmp, {"files": {"ccr/a.py": entry(75.0)}})
            passing, _ = self._run_main(["coverage_floor.py", path, "70"])
            failing, _ = self._run_main(["coverage_floor.py", path, "90"])
        self.assertEqual(passing, 0)
        self.assertEqual(failing, 1)

    def test_invalid_floor_is_rejected_before_reading_the_report(self):
        # nan/inf make every `percent < floor` comparison False, and -1/101
        # are outside the only range a percentage can have. The report path is
        # missing so a validating main reports the floor, not the file.
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "absent.json")
            for value in ("nan", "inf", "-1", "101", "not-a-number"):
                with self.subTest(floor=value):
                    code, output = self._run_main(
                        ["coverage_floor.py", missing, value])
                    self.assertEqual(code, 1)
                    self.assertIn("[ERROR] invalid floor: " + value, output)
                    self.assertNotIn("cannot read coverage report", output)

    def test_invalid_floor_exits_one_from_the_script(self):
        result = self._run_script("absent-coverage.json", "nan")
        self.assertEqual(result.returncode, 1)
        self.assertIn("[ERROR] invalid floor: nan", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_boundary_floors_are_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_report(tmp, {"files": {"ccr/a.py": entry(100.0)}})
            code, output = self._run_main(["coverage_floor.py", path, "100"])
        self.assertEqual(code, 0)
        self.assertIn("[SUCCESS] all modules >= 100.0%", output)

    def test_missing_report_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "absent.json")
            result = self._run_script(path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("[ERROR] cannot read coverage report " + path,
                      result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_malformed_report_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "coverage.json"
            path.write_text("{not json", encoding="utf-8")
            result = self._run_script(str(path))
        self.assertEqual(result.returncode, 1)
        self.assertIn("[ERROR] cannot read coverage report " + str(path),
                      result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_files_value_that_is_not_an_object_exits_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_report(tmp, {"files": ["ccr/a.py"]})
            result = self._run_script(path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("[ERROR] cannot read coverage report " + path,
                      result.stdout)
        self.assertIn("files object", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_file_entry_that_is_not_an_object_exits_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_report(tmp, {"files": {"ccr/a.py": 95.0}})
            result = self._run_script(path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("[ERROR] cannot read coverage report " + path,
                      result.stdout)
        self.assertIn("file entries must be JSON objects", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_scalar_summary_exits_cleanly(self):
        # A truthy non-object summary used to reach summary.get() and raise
        # an uncaught AttributeError.
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_report(tmp, {"files": {"ccr/a.py": {"summary": 5}}})
            result = self._run_script(path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("[ERROR] cannot read coverage report " + path,
                      result.stdout)
        self.assertIn("file summary must be a JSON object, got int",
                      result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_module_guard_turns_main_result_into_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_report(tmp, {"files": {"ccr/a.py": entry(70.0)}})
            argv = ["coverage_floor.py", path]
            with mock.patch.object(sys, "argv", argv), \
                    contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    runpy.run_path(str(SCRIPT), run_name="__main__")
        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
