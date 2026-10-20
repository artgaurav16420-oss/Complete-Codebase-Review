"""Tests for ccr.manifest: loading, validation, and helpers."""

import copy
import json
import re
import unittest
from pathlib import Path

from ccr import manifest as manifest_mod

ROOT = Path(__file__).resolve().parent.parent


class TestManifestLoad(unittest.TestCase):
    """Manifest loads and validates."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = manifest_mod.load()

    def test_has_fourteen_agents(self):
        self.assertEqual(len(self.manifest["agents"]), 14)

    def test_has_twelve_env_vars(self):
        self.assertEqual(len(self.manifest["env_vars"]), 12)

    def test_agent_ids_helper(self):
        ids = manifest_mod.agent_ids(self.manifest)
        self.assertIn("security", ids)
        self.assertIn("process_quality", ids)

    def test_report_name(self):
        self.assertEqual(
            manifest_mod.report_name(self.manifest, "code_quality"),
            "Code Quality",
        )

    def test_unknown_agent_raises(self):
        with self.assertRaises(ValueError):
            manifest_mod.report_name(self.manifest, "nope")

    def test_floor_for_known_and_unknown(self):
        self.assertEqual(
            manifest_mod.floor_for(self.manifest, "circular_dependency"), 8.0
        )
        self.assertEqual(manifest_mod.floor_for(self.manifest, "other"), 1.0)

    def test_version_matches_pyproject(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        version = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text).group(1)
        self.assertEqual(self.manifest["version"], version)

    def test_version_matches_skill_frontmatter(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        version = re.search(r"(?m)^version:\s*(\S+)", text).group(1)
        self.assertEqual(self.manifest["version"], version)


class TestManifestValidation(unittest.TestCase):
    """Invalid manifests are rejected with ValueError."""

    @classmethod
    def setUpClass(cls):
        with open(ROOT / "ccr" / "pipeline.json", encoding="utf-8") as f:
            cls.base = json.load(f)

    def _broken(self):
        return copy.deepcopy(self.base)

    def test_missing_key(self):
        data = self._broken()
        del data["thresholds"]
        with self.assertRaises(ValueError):
            manifest_mod.validate(data)

    def test_duplicate_agent(self):
        data = self._broken()
        data["agents"].append(dict(data["agents"][0]))
        with self.assertRaises(ValueError):
            manifest_mod.validate(data)

    def test_duplicate_env_var(self):
        data = self._broken()
        data["env_vars"].append(dict(data["env_vars"][0]))
        with self.assertRaises(ValueError):
            manifest_mod.validate(data)

    def test_threshold_out_of_range(self):
        data = self._broken()
        data["thresholds"]["full_completion"] = 1.5
        with self.assertRaises(ValueError):
            manifest_mod.validate(data)

    def test_quick_agent_unknown(self):
        data = self._broken()
        data["thresholds"]["quick_agents"].append("ghost")
        with self.assertRaises(ValueError):
            manifest_mod.validate(data)

    def test_missing_agent_field(self):
        data = self._broken()
        del data["agents"][0]["coverage"]
        with self.assertRaises(ValueError):
            manifest_mod.validate(data)

    def test_not_an_object(self):
        with self.assertRaises(ValueError):
            manifest_mod.validate([])

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            manifest_mod.load(ROOT / "does-not-exist.json")


if __name__ == "__main__":
    unittest.main()
