#!/usr/bin/env bash
# Mock Validation Test Suite
#
# Validates SKILL.md against expected content requirements, runs
# a mock skill evaluation against expected_issues.json, and
# runs all Python unit tests.
#
# Usage: ./test.sh [--skill-checks-only]
#
#   --skill-checks-only  Run only the SKILL.md / karpathy-guidelines.md
#                        contract checks and exit.
#
# Returns 0 if all checks pass, 1 otherwise.
set -euo pipefail

SKILL_CHECKS_ONLY=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --skill-checks-only) SKILL_CHECKS_ONLY=1 ;;
        -h|--help)
            echo "Usage: ./test.sh [--skill-checks-only]"
            exit 0
            ;;
        *)
            echo "[ERROR] Unknown argument: $1" >&2
            exit 2
            ;;
    esac
    shift
done

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

if [ "$SKILL_CHECKS_ONLY" -eq 1 ]; then
    if [ "$FAIL" -eq 1 ]; then
        echo "[ERROR] Skill checks failed!"
        exit 1
    fi
    echo "[SUCCESS] Skill checks passed"
    exit 0
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

echo "[INFO] Running docs and compliance suite..."
"$PYTHON" tests/compliance_test.py || FAIL=1
"$PYTHON" tests/review_compliance_test.py || FAIL=1

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
