"""Fail when any source module falls below a per-file coverage floor.

Reads a JSON report produced by ``coverage json``. The module-level
``fail_under`` gate covers the project total; this catches a single module
regressing while the total stays green.
"""

import json
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
        # `coverage json` writes a JSON number here. `float()` would also
        # accept the string "100" or the boolean true, so a malformed report
        # could pass the gate; only int/float count (bool is an int subclass).
        # The range check keeps 150 and -1 out, and it also rejects NaN (every
        # comparison is False) and the infinities (both exceed 100), so no
        # separate finiteness test is needed.
        valid = (
            isinstance(percent, (int, float))
            and not isinstance(percent, bool)
            and 0 <= percent <= 100
        )
        if not valid:
            failures.append((path, 0.0))
        elif percent < floor:
            failures.append((path, float(percent)))
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
    # `float` only yields a finite value or an infinity here, and the range
    # check rejects both infinities and NaN, so no separate finiteness test.
    if not 0.0 <= floor <= 100.0:
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
