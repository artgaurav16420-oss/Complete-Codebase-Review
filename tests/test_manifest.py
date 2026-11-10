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

    def test_env_var_names(self):
        dummy_manifest = {
            "env_vars": [
                {"name": "CODE_REVIEW_EFFORT"},
                {"name": "CODE_REVIEW_TIMEOUT_SEC"}
            ]
        }
        names = manifest_mod.env_var_names(dummy_manifest)
        self.assertEqual(names, ["CODE_REVIEW_EFFORT", "CODE_REVIEW_TIMEOUT_SEC"])

    def test_unknown_agent_raises(self):
        with self.assertRaises(ValueError):
            manifest_mod.report_name(self.manifest, "nope")

    def test_floor_for_known_and_unknown(self):
        self.assertEqual(
            manifest_mod.floor_for(self.manifest, "circular_dependency"), 8.0
        )
        self.assertEqual(manifest_mod.floor_for(self.manifest, "other"), 1.0)

    def test_load_pushes_calibration_into_findings(self):
        from ccr import findings as findings_mod
        calibration = self.manifest["calibration"]
        self.assertEqual(findings_mod.OVERLAP_THRESHOLD,
                         calibration["overlap_threshold"])
        self.assertEqual(findings_mod.LARGE_FIX_HOURS,
                         calibration["large_fix_hours"])
        self.assertEqual(findings_mod.QUICK_WIN_CAP_HOURS,
                         calibration["quick_win_cap_hours"])

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

    def test_non_string_agent_alias(self):
        data = self._broken()
        data["agents"][0]["report"] = 7
        with self.assertRaises(ValueError) as ctx:
            manifest_mod.validate(data)
        self.assertIn("must be a string", str(ctx.exception))

    def test_agent_id_may_not_use_the_result_file_prefix(self):
        # A result is phase_<id>.json. An agent called phase_security would
        # name its fixture exactly as the canonical result of agent security.
        data = self._broken()
        data["agents"][0]["id"] = "phase_security"
        with self.assertRaises(ValueError) as ctx:
            manifest_mod.validate(data)
        self.assertIn("reserved prefix", str(ctx.exception))

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

    def test_calibration_out_of_range(self):
        data = self._broken()
        data["calibration"]["overlap_threshold"] = 1.5
        with self.assertRaises(ValueError):
            manifest_mod.validate(data)

    def test_calibration_unknown_key(self):
        data = self._broken()
        data["calibration"]["ghost"] = 1.0
        with self.assertRaises(ValueError) as ctx:
            manifest_mod.validate(data)
        self.assertIn("unknown key", str(ctx.exception))

    def test_calibration_bool_rejected(self):
        data = self._broken()
        data["calibration"]["large_fix_hours"] = True
        with self.assertRaises(ValueError):
            manifest_mod.validate(data)

    def test_calibration_overflowing_int_rejected(self):
        data = self._broken()
        data["calibration"]["large_fix_hours"] = 10 ** 400
        with self.assertRaises(ValueError) as ctx:
            manifest_mod.validate(data)
        self.assertIn("out of range", str(ctx.exception))

    def test_calibration_is_optional(self):
        data = self._broken()
        del data["calibration"]
        manifest_mod.validate(data)

    def test_tech_debt_label_missing(self):
        data = self._broken()
        del data["tech_debt_labels"]["circular_dependency"]
        with self.assertRaises(ValueError) as ctx:
            manifest_mod.validate(data)
        self.assertIn("missing", str(ctx.exception))

    def test_tech_debt_label_for_unknown_floor(self):
        data = self._broken()
        data["tech_debt_labels"]["ghost"] = "Ghost"
        with self.assertRaises(ValueError) as ctx:
            manifest_mod.validate(data)
        self.assertIn("unknown floor", str(ctx.exception))

    def test_tech_debt_labels_must_be_object(self):
        data = self._broken()
        data["tech_debt_labels"] = []
        with self.assertRaises(ValueError):
            manifest_mod.validate(data)

    def test_tech_debt_labels_are_optional(self):
        data = self._broken()
        del data["tech_debt_labels"]
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

    def test_manifest_severity_drift_is_rejected(self):
        """A severity the code does not enforce fails at load, not silently later."""
        data = self._broken()
        data["severities"] = [
            "CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "BLOCKER",
        ]
        with self.assertRaises(ValueError) as ctx:
            manifest_mod.validate(data)
        message = str(ctx.exception)
        self.assertIn("severities", message)
        self.assertIn("BLOCKER", message)
        self.assertIn("CRITICAL", manifest_mod.load()["severities"])

    def test_not_an_object(self):
        with self.assertRaises(ValueError):
            manifest_mod.validate([])

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            manifest_mod.load(ROOT / "does-not-exist.json")


class TestBaseAgents(unittest.TestCase):
    def test_manifest_lists_base_agents(self):
        manifest = manifest_mod.load()
        self.assertTrue(manifest["base_agents"])
        ids = manifest_mod.agent_ids(manifest)
        for agent_id in manifest["base_agents"]:
            self.assertIn(agent_id, ids)

    def test_unknown_base_agent_rejected(self):
        manifest = copy.deepcopy(manifest_mod.load())
        manifest["base_agents"].append("does_not_exist")
        with self.assertRaises(ValueError):
            manifest_mod.validate(manifest)

    def test_non_string_base_agent_rejected(self):
        manifest = copy.deepcopy(manifest_mod.load())
        manifest["base_agents"] = [1]
        with self.assertRaises(ValueError):
            manifest_mod.validate(manifest)


if __name__ == "__main__":
    unittest.main()
