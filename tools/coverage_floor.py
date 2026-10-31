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
        if percent is None:
            failures.append((path, 0.0))
        elif percent < floor:
            failures.append((path, percent))
    if checked == 0:
        return [("<no files checked>", 0.0)]
    return failures


def main(argv):
    path = argv[1] if len(argv) > 1 else "coverage.json"
    floor = float(argv[2]) if len(argv) > 2 else DEFAULT_FLOOR
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
