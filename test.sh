#!/usr/bin/env bash
# Mock Validation Test Suite
#
# Validates SKILL.md against expected content requirements and runs
# a mock skill evaluation against expected_issues.json.
#
# Usage: ./test.sh
#
# Returns 0 if all checks pass, 1 otherwise.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "[INFO] Starting Mock Validation Test Suite"

TEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ccr-dummy-repo.XXXXXX")"
cat << 'CODE' > "$TEST_DIR/app.py"
import os
import subprocess
import sys

def login(user, password):
    expected = os.environ["TEST_CREDENTIAL"]
    if password == expected:
        return True
    return False

def ping_host(host):
    # Intentional vulnerable fixture for integration tests: CWE-78.
    subprocess.run(["ping", "-c", "1", host], check=False)
CODE

echo "[INFO] Created dummy test repo at $TEST_DIR"

SKILL_FILE="SKILL.md"
FAIL=0

if ! grep -q "🔧 Environment Variables" "$SKILL_FILE"; then
    echo "[ERROR] '🔧 Environment Variables' section missing from $SKILL_FILE"
    FAIL=1
fi

if ! grep -q "💾 Checkpointing" "$SKILL_FILE"; then
    echo "[ERROR] '💾 Checkpointing' section missing from $SKILL_FILE"
    FAIL=1
fi

if ! grep -q "⚡ Quick Mode" "$SKILL_FILE"; then
    echo "[ERROR] '⚡ Quick Mode' section missing from $SKILL_FILE"
    FAIL=1
fi

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

echo "[INFO] Validating expected issues JSON..."

python3 -c "
import json
import sys

try:
    with open('tests/expected_issues.json', encoding='utf-8') as f:
        issues = json.load(f)

    assert isinstance(issues, list), 'Expected issues must be a list'
    assert len(issues) > 0, 'Expected issues list cannot be empty'

    for issue in issues:
        assert isinstance(issue, str) and issue.strip(), f'Invalid issue format: {issue}'

    print(f'[SUCCESS] Validated {len(issues)} expected issues from JSON.')

except Exception as e:
    print(f'[ERROR] expected_issues.json validation failed: {e}')
    sys.exit(1)
" || FAIL=1

rm -rf "$TEST_DIR"

if [ "$FAIL" -eq 1 ]; then
    echo "[ERROR] Tests failed!"
    false
else
    echo "[SUCCESS] All tests passed! SKILL.md is production-grade."
fi
