"""Tests for tools.coverage_floor."""

import unittest

from tools.coverage_floor import check


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


if __name__ == "__main__":
    unittest.main()
