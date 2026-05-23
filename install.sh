#!/usr/bin/env bash
set -euo pipefail

SKILL_NAME="complete-codebase-review"
SRC="$(cd "$(dirname "$0")" && pwd)"
TARGET="$HOME/.claude/skills/$SKILL_NAME"

echo "Installing $SKILL_NAME to $TARGET ..."

mkdir -p "$TARGET/tests"
cp "$SRC/SKILL.md" "$TARGET/SKILL.md"
cp "$SRC/tests/"* "$TARGET/tests/"

SKILL_FILE="$TARGET/SKILL.md"
if [ -f "$SKILL_FILE" ]; then
    LINES=$(wc -l < "$SKILL_FILE")
    echo "  Installed: $SKILL_FILE ($LINES lines)"
    echo "  Invoke with: /complete-codebase-review [path]"
else
    echo "  Install failed: $SKILL_FILE not found" >&2
    exit 1
fi
