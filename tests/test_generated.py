"""Tests for tools/generate.py and the generated artifacts."""

import contextlib
import hashlib
import io
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ccr import manifest as manifest_mod

ROOT = Path(__file__).resolve().parent.parent

import sys
sys.path.insert(0, str(ROOT))
from tools import generate  # noqa: E402


def _quiet(func, *args, **kwargs):
    """Run func with stdout captured."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        return func(*args, **kwargs), buffer.getvalue()


class TestGeneratedArtifacts(unittest.TestCase):
    """Committed generated files match the manifest."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = manifest_mod.load()

    def test_check_mode_passes(self):
        code, output = _quiet(generate.run, True)
        self.assertEqual(code, 0, output)

    def test_skill_tables_match_manifest(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        env_block = re.search(
            r"<!-- BEGIN GENERATED: skill-env-vars -->(.*?)"
            r"<!-- END GENERATED: skill-env-vars -->",
            text, re.DOTALL,
        ).group(1)
        self.assertEqual(
            len([line for line in env_block.splitlines() if line.startswith("|")]),
            len(self.manifest["env_vars"]) + 2,
        )
        agent_block = re.search(
            r"<!-- BEGIN GENERATED: skill-specialist-agents -->(.*?)"
            r"<!-- END GENERATED: skill-specialist-agents -->",
            text, re.DOTALL,
        ).group(1)
        self.assertEqual(
            len([line for line in agent_block.splitlines() if line.startswith("|")]),
            len(self.manifest["agents"]) + 2,
        )

    def test_checksum_matches_installer(self):
        digest = hashlib.sha256((ROOT / "install.py").read_bytes()).hexdigest()
        stored = (ROOT / "install.py.sha256").read_text(encoding="utf-8")
        self.assertEqual(stored.split()[0], digest)

    def test_changelog_matches_manifest(self):
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        version = re.search(r"(?m)^## v([^\s(]+)", text).group(1)
        self.assertEqual(version, self.manifest["version"])

    def test_readme_env_table_matches_manifest(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        block = re.search(
            r"<!-- BEGIN GENERATED: readme-env-vars -->(.*?)"
            r"<!-- END GENERATED: readme-env-vars -->",
            text, re.DOTALL,
        ).group(1)
        for var in self.manifest["env_vars"]:
            self.assertIn("`" + var["name"] + "`", block)

    def test_env_config_table_vars_match_manifest(self):
        from tests.test_env_config import TABLE_VARS
        self.assertEqual(
            TABLE_VARS, [var["name"] for var in self.manifest["env_vars"]]
        )

    def test_compliance_agent_list_matches_manifest(self):
        from tests.test_compliance import _ALL_AGENTS
        names = {agent["name"] for agent in self.manifest["agents"]}
        self.assertEqual(set(_ALL_AGENTS), names)

    def test_help_version_matches_manifest(self):
        text = (ROOT / "help.md").read_text(encoding="utf-8")
        self.assertIn(
            "Synced with SKILL.md v" + self.manifest["version"], text
        )


class TestWritePath(unittest.TestCase):
    """Generation writes files and is idempotent in a temp tree."""

    def _tree(self, root):
        """Create a minimal repo tree with all generated markers."""
        blocks = (
            "<!-- BEGIN GENERATED: skill-env-vars -->\n"
            "<!-- END GENERATED: skill-env-vars -->\n"
            "<!-- BEGIN GENERATED: skill-canonical-domains -->\n"
            "<!-- END GENERATED: skill-canonical-domains -->\n"
            "<!-- BEGIN GENERATED: skill-specialist-agents -->\n"
            "<!-- END GENERATED: skill-specialist-agents -->\n"
        )
        (root / "SKILL.md").write_text(
            "version: 0.0.0\n" + blocks, encoding="utf-8"
        )
        for name, key in (
            ("README.md", "readme-env-vars"),
            ("help.md", "help-env-vars"),
            ("orchestrator-rules.md", "orchestrator-env-vars"),
        ):
            (root / name).write_text(
                "<!-- BEGIN GENERATED: {} -->\n"
                "<!-- END GENERATED: {} -->\n".format(key, key),
                encoding="utf-8",
            )
        (root / "pyproject.toml").write_text(
            'version = "0.0.0"\n', encoding="utf-8"
        )
        (root / "install.py").write_text("print('x')\n", encoding="utf-8")
        (root / "install.py.sha256").write_text("", encoding="utf-8")

    def test_writes_and_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._tree(root)
            with patch.object(generate, "REPO_ROOT", root), \
                 patch.object(generate, "MANIFEST", ROOT / "ccr" / "pipeline.json"):
                code, _ = _quiet(generate.run, False)
                self.assertEqual(code, 0)
                self.assertIn(
                    "`CODE_REVIEW_FORMAT`",
                    (root / "SKILL.md").read_text(encoding="utf-8"),
                )
                code, _ = _quiet(generate.run, True)
                self.assertEqual(code, 0)

    def test_stale_check_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._tree(root)
            with patch.object(generate, "REPO_ROOT", root), \
                 patch.object(generate, "MANIFEST", ROOT / "ccr" / "pipeline.json"):
                _quiet(generate.run, False)
                readme = root / "README.md"
                marker = "<!-- BEGIN GENERATED: readme-env-vars -->"
                readme.write_text(
                    readme.read_text(encoding="utf-8").replace(
                        marker, marker + "\n| stale | row | here |", 1
                    ),
                    encoding="utf-8",
                )
                code, output = _quiet(generate.run, True)
                self.assertEqual(code, 1)
                self.assertIn("[STALE]", output)


if __name__ == "__main__":
    unittest.main()
