"""Fail when any source module falls below a per-file coverage floor.

Reads a JSON report produced by ``coverage json``. The module-level
``fail_under`` gate covers the project total; this catches a single module
regressing while the total stays green.
"""

import json
import math
import sys
from pathlib import Path

DEFAULT_FLOOR = 80.0
EXCLUDED_DIRS = {"tests", "tools"}
EXCLUDED_NAMES = {"__main__.py"}


def _skipped(path):
    parts = Path(path.replace("\\", "/")).parts
    if parts and parts[-1] in EXCLUDED_NAMES:
        return True
    return any(part in EXCLUDED_DIRS for part in parts)


def check(report, floor=DEFAULT_FLOOR):
    files = report.get("files") or {}
    if not files:
        return [("<empty report>", 0.0)]
    failures = []
    checked = 0
    for path, data in sorted(files.items()):
        if _skipped(path):
            continue
        checked += 1
        summary = data.get("summary")
        if not summary:
            failures.append((path, 0.0))
            continue
        percent = summary.get("percent_covered")
        # json.load accepts NaN, Infinity and huge integers; NaN < floor is
        # always False and math.isfinite(10**400) raises OverflowError, so
        # coerce first and fail anything that cannot be a finite float.
        try:
            percent = float(percent)
            valid = math.isfinite(percent)
        except (OverflowError, TypeError, ValueError):
            valid = False
        if not valid:
            failures.append((path, 0.0))
        elif percent < floor:
            failures.append((path, percent))
    if checked == 0:
        return [("<no files checked>", 0.0)]
    return failures


def _shape_error(report):
    """Describe why a report cannot be coverage JSON, or return ""."""
    files = report.get("files")
    if files is not None and not isinstance(files, dict):
        return "expected a files object, got " + type(files).__name__
    if isinstance(files, dict):
        for entry in files.values():
            if not isinstance(entry, dict):
                return ("file entries must be JSON objects, got "
                        + type(entry).__name__)
            summary = entry.get("summary")
            if summary is not None and not isinstance(summary, dict):
                return ("file summary must be a JSON object, got "
                        + type(summary).__name__)
    return ""


def _parse_floor(value):
    """Return the floor as a finite float in 0..100, or None when invalid.

    ``float`` accepts "nan" and "inf", and every ``percent < nan`` comparison
    is False, so an unvalidated floor silently disables the gate.
    """
    try:
        floor = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(floor) or not 0.0 <= floor <= 100.0:
        return None
    return floor


def main(argv):
    path = argv[1] if len(argv) > 1 else "coverage.json"
    if len(argv) > 2:
        floor = _parse_floor(argv[2])
        if floor is None:
            print("[ERROR] invalid floor: " + argv[2])
            return 1
    else:
        floor = DEFAULT_FLOOR
    try:
        with open(path, encoding="utf-8") as handle:
            report = json.load(handle)
    except (OSError, ValueError) as exc:
        print("[ERROR] cannot read coverage report {}: {}".format(path, exc))
        return 1
    if not isinstance(report, dict):
        print("[ERROR] cannot read coverage report {}: expected a JSON object, "
              "got {}".format(path, type(report).__name__))
        return 1
    shape_error = _shape_error(report)
    if shape_error:
        print("[ERROR] cannot read coverage report {}: {}".format(
            path, shape_error))
        return 1
    failures = check(report, floor)
    for path, percent in failures:
        print("[FAIL] {}: {:.1f}% < {:.1f}%".format(path, percent, floor))
    if failures:
        print("[FAIL] {} module(s) below the per-file floor".format(len(failures)))
        return 1
    print("[SUCCESS] all modules >= {:.1f}%".format(floor))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
