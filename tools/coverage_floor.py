"""Fail when any source module falls below a per-file coverage floor.

Reads a JSON report produced by ``coverage json``. The module-level
``fail_under`` gate covers the project total; this catches a single module
regressing while the total stays green.
"""

import json
import sys

DEFAULT_FLOOR = 80.0
EXCLUDED = ("__main__.py", "tests/", "tools/")


def check(report, floor=DEFAULT_FLOOR):
    failures = []
    for path, data in sorted(report.get("files", {}).items()):
        if any(token in path for token in EXCLUDED):
            continue
        percent = data.get("summary", {}).get("percent_covered", 100.0)
        if percent < floor:
            failures.append((path, percent))
    return failures


def main(argv):
    path = argv[1] if len(argv) > 1 else "coverage.json"
    floor = float(argv[2]) if len(argv) > 2 else DEFAULT_FLOOR
    with open(path, encoding="utf-8") as handle:
        report = json.load(handle)
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
