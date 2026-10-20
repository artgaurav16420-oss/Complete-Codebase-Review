#!/usr/bin/env python3
"""Generate documentation tables from ccr/pipeline.json.

Single source of truth: ccr/pipeline.json. This script rewrites the env-var
tables, agent tables, version strings, and the installer checksum. Run it
after editing the manifest, then commit the generated files.

Usage:
    python tools/generate.py
    python tools/generate.py --check   # CI mode: fail if anything is stale
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "ccr" / "pipeline.json"

BEGIN = "<!-- BEGIN GENERATED: {} -->"
END = "<!-- END GENERATED: {} -->"


def load_manifest():
    """Load and return the pipeline manifest."""
    with open(MANIFEST, encoding="utf-8") as f:
        return json.load(f)


def replace_block(text, key, body):
    """Replace the content between generated markers. Raises ValueError."""
    begin = BEGIN.format(key)
    end = END.format(key)
    start = text.find(begin)
    if start < 0:
        raise ValueError("missing marker: " + begin)
    stop = text.find(end, start)
    if stop < 0:
        raise ValueError("missing marker: " + end)
    return text[:start + len(begin)] + "\n\n" + body + "\n\n" + text[stop:]


def env_table_section(manifest):
    """Render the full env-var table (header, separator, rows)."""
    lines = [
        "| Variable | Default | Description |",
        "|----------|---------|-------------|",
    ]
    for var in manifest["env_vars"]:
        lines.append(
            "| `{name}` | `{default}` | {description} |".format(**var)
        )
    return "\n".join(lines)


def canonical_section(manifest):
    """Render the full canonical domain table."""
    lines = [
        "| Canonical ID | Agent Name | Report Name |",
        "|-------------|------------|-------------|",
    ]
    for agent in manifest["agents"]:
        lines.append("| `{id}` | {name} | {report} |".format(**agent))
    return "\n".join(lines)


def specialist_section(manifest):
    """Render the full specialist agent table."""
    lines = [
        "| Agent | Coverage | Suggested Skill |",
        "|-------|----------|----------------|",
    ]
    for agent in manifest["agents"]:
        lines.append(
            "| {name} | {coverage} | {skill} |".format(**agent)
        )
    return "\n".join(lines)


def env_bullets(manifest):
    """Render help.md-style bullet list for env vars."""
    rows = []
    for var in manifest["env_vars"]:
        rows.append(
            "*   `{name}` (default: `{default}`): {description}".format(**var)
        )
    return "\n".join(rows)


def env_inline_list(manifest):
    """Render a comma-separated backticked list for orchestrator-rules."""
    return ", ".join("`" + v["name"] + "`" for v in manifest["env_vars"])


def render_text(path, manifest):
    """Return the regenerated text for a doc file."""
    text = path.read_text(encoding="utf-8")
    name = path.name
    if name == "SKILL.md":
        text = replace_block(text, "skill-env-vars", env_table_section(manifest))
        text = replace_block(
            text, "skill-canonical-domains", canonical_section(manifest)
        )
        text = replace_block(
            text, "skill-specialist-agents", specialist_section(manifest)
        )
        text = re.sub(
            r"(?m)^version:\s*\S+$",
            "version: " + manifest["version"],
            text,
            count=1,
        )
    elif name == "README.md":
        text = replace_block(text, "readme-env-vars", env_table_section(manifest))
    elif name == "help.md":
        text = replace_block(text, "help-env-vars", env_bullets(manifest))
    elif name == "orchestrator-rules.md":
        text = replace_block(
            text, "orchestrator-env-vars", env_inline_list(manifest)
        )
    return text


def render_pyproject(manifest):
    """Return pyproject.toml text with the manifest version applied."""
    path = REPO_ROOT / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    return re.sub(
        r'(?m)^version\s*=\s*"[^"]+"',
        'version = "' + manifest["version"] + '"',
        text,
        count=1,
    )


def render_checksum():
    """Return install.py.sha256 content."""
    script = REPO_ROOT / "install.py"
    digest = hashlib.sha256(script.read_bytes()).hexdigest()
    return digest + "  install.py\n"


def targets(manifest):
    """Return list of (path, expected_text) pairs to compare or write."""
    pairs = []
    for name in ["SKILL.md", "README.md", "help.md", "orchestrator-rules.md"]:
        path = REPO_ROOT / name
        pairs.append((path, render_text(path, manifest)))
    pairs.append((REPO_ROOT / "pyproject.toml", render_pyproject(manifest)))
    pairs.append((REPO_ROOT / "install.py.sha256", render_checksum()))
    return pairs


def run(check_only):
    """Generate all targets, or verify they are current. Returns exit code."""
    manifest = load_manifest()
    stale = []
    for path, expected in targets(manifest):
        current = path.read_text(encoding="utf-8")
        if current == expected:
            continue
        stale.append(path)
        if not check_only:
            crlf = b"\r\n" in path.read_bytes()
            newline = "\r\n" if crlf else "\n"
            path.write_text(expected, encoding="utf-8", newline=newline)
    if check_only:
        for path in stale:
            print("[STALE] " + str(path.relative_to(REPO_ROOT)))
        if stale:
            print("[ERROR] Generated files are stale. Run: python tools/generate.py")
            return 1
        print("[SUCCESS] All generated files are current.")
        return 0
    for path in stale:
        print("[UPDATED] " + str(path.relative_to(REPO_ROOT)))
    if not stale:
        print("[SUCCESS] Nothing to update.")
    return 0


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate docs from ccr/pipeline.json."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if any generated file is stale (CI mode).",
    )
    args = parser.parse_args()
    sys.exit(run(args.check))


if __name__ == "__main__":
    main()
