#!/usr/bin/env bash
# Mock Validation Test Suite
#
# Validates SKILL.md against expected content requirements, runs
# a mock skill evaluation against expected_issues.json, and
# runs all Python unit tests.
#
# Usage: ./test.sh
#
# Returns 0 if all checks pass, 1 otherwise.
set -euo pipefail

PYTHON=$(command -v python3 || command -v python || echo "python")

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "[INFO] Starting Mock Validation Test Suite"

SKILL_FILE="SKILL.md"
FAIL=0

if grep -q "^model: " "$SKILL_FILE"; then
    echo "[ERROR] Hardcoded 'model: ' still present in $SKILL_FILE frontmatter or templates"
    FAIL=1
fi

if ! grep -q "effort: \${CODE_REVIEW_EFFORT:-max}" "$SKILL_FILE"; then
    echo "[ERROR] Dynamic effort not found in $SKILL_FILE"
    FAIL=1
fi

if [ ! -f "karpathy-guidelines.md" ]; then
    echo "[ERROR] karpathy-guidelines.md missing — Process Quality agent will fail"
    FAIL=1
else
    echo "[SUCCESS] karpathy-guidelines.md exists"
fi

echo "[INFO] Checking generated docs are current..."
if "$PYTHON" tools/generate.py --check; then
    echo "[SUCCESS] Generated docs are current"
else
    echo "[ERROR] Generated docs are stale — run: python tools/generate.py"
    FAIL=1
fi

echo "[INFO] Running eval harness against recorded fixtures..."

if "$PYTHON" -m ccr eval; then
    echo "[SUCCESS] Eval harness covered all expected issues"
else
    echo "[ERROR] Eval harness missed expected issues"
    FAIL=1
fi

echo "[INFO] Running all unit tests..."
if "$PYTHON" -c "import coverage" >/dev/null 2>&1; then
    "$PYTHON" -m coverage run -m unittest discover -s tests -p "test_*.py" || FAIL=1
    "$PYTHON" -m coverage report || FAIL=1
else
    echo "[INFO] coverage not available — running without coverage"
    "$PYTHON" -m unittest discover -s tests -p "test_*.py" || FAIL=1
fi

if [ "$FAIL" -eq 1 ]; then
    echo "[ERROR] Tests failed!"
    false
else
    echo "[SUCCESS] All tests passed! SKILL.md is production-grade."
fi
