"""Tests for ccr.providers: prompts, ingestion, fixture replay."""

import json
import tempfile
import unittest
from pathlib import Path

from ccr import manifest as manifest_mod
from ccr import providers

ROOT = Path(__file__).resolve().parent.parent


class TestPrompt(unittest.TestCase):
    """Prompt hardening requirements."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = manifest_mod.load()
        cls.agent = cls.manifest["agents"][2]

    def test_prompt_contains_skill_dir(self):
        prompt = providers.build_prompt(self.agent, "/tmp/repo", "/skills/ccr")
        self.assertIn("SKILL_DIR=/skills/ccr", prompt)

    def test_prompt_requests_da_verdict(self):
        prompt = providers.build_prompt(self.agent, "/tmp/repo", "/skills/ccr")
        self.assertIn('"da_verdict"', prompt)

    def test_prompt_scopes_to_one_domain(self):
        prompt = providers.build_prompt(self.agent, "/tmp/repo", "/skills/ccr")
        self.assertIn("Focus ONLY on", prompt)
        self.assertIn("Do NOT flag adjacent domains", prompt)

    def test_prompt_defines_hours_and_design_notes(self):
        prompt = providers.build_prompt(self.agent, "/tmp/repo", "/skills/ccr")
        self.assertIn("cost of the FIX", prompt)
        self.assertIn("design_note", prompt)

    def test_prompt_requires_reproduction_for_high(self):
        prompt = providers.build_prompt(self.agent, "/tmp/repo", "/skills/ccr")
        self.assertIn("reproduction path", prompt)

    def test_prompt_includes_domain_checks(self):
        agents = {a["id"]: a for a in self.manifest["agents"]}
        build = providers.build_prompt(
            agents["build_ci"], "/tmp/repo", "/skills/ccr"
        )
        self.assertIn("mocha 11 needs Node", build)
        quality = providers.build_prompt(
            agents["code_quality"], "/tmp/repo", "/skills/ccr"
        )
        self.assertIn("RegExp.exec without /g", quality)

    def test_prompt_contains_contract(self):
        prompt = providers.build_prompt(self.agent, "/tmp/repo", "/skills/ccr")
        self.assertIn("[path/file.py:42]", prompt)
        self.assertIn("GATE: COMPLETE", prompt)
        self.assertIn(self.agent["coverage"], prompt)

    def test_missing_skill_dir_placeholder(self):
        prompt = providers.build_prompt(self.agent, "/tmp/repo", "")
        self.assertIn("<SKILL_DIR>", prompt)

    def test_prompt_carries_manifest_version(self):
        prompt = providers.build_prompt(
            self.agent, "/tmp/repo", "/skills/ccr", manifest_version="2.4.0"
        )
        self.assertIn("MANIFEST_VERSION=2.4.0", prompt)

    def test_write_prompts_embeds_manifest_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = {"agents": ["security"], "target": "/tmp/x"}
            paths = providers.write_prompts(
                self.manifest, plan, tmp, skill_dir="/skills/ccr"
            )
            text = paths[0].read_text(encoding="utf-8")
        self.assertIn(
            "MANIFEST_VERSION=" + self.manifest["version"], text
        )

    def test_write_prompts(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = {"agents": ["security", "architecture"], "target": "/tmp/x"}
            paths = providers.write_prompts(
                self.manifest, plan, tmp, skill_dir="/skills/ccr"
            )
            self.assertEqual(len(paths), 2)
            self.assertTrue(paths[0].exists())
            self.assertEqual(
                sorted(p.name for p in paths),
                ["phase_architecture.prompt.md", "phase_security.prompt.md"],
            )


class TestLoadResults(unittest.TestCase):
    """Result ingestion and validation."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, data):
        (self.dir / name).write_text(json.dumps(data), encoding="utf-8")

    def test_load_phase_file(self):
        self._write("phase_security.json", {"findings": []})
        results = providers.load_results(self.dir, ["security"])
        self.assertIn("security", results)

    def test_load_plain_fixture_name(self):
        self._write("security.json", {"findings": []})
        results = providers.load_results(self.dir, ["security"])
        self.assertIn("security", results)

    def test_missing_required_raises(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            providers.load_results(self.dir, ["security"])
        self.assertIn("security", str(ctx.exception))

    def test_missing_optional_returns_subset(self):
        self._write("security.json", {"findings": []})
        results = providers.load_results(
            self.dir, ["security", "architecture"], required=False
        )
        self.assertEqual(list(results), ["security"])

    def test_rejects_non_object(self):
        self._write("security.json", [])
        with self.assertRaises(ValueError):
            providers.load_result(self.dir / "security.json", "security")

    def test_rejects_missing_findings(self):
        self._write("security.json", {"agent": "security"})
        with self.assertRaises(ValueError):
            providers.load_result(self.dir / "security.json", "security")

    def test_rejects_bad_finding(self):
        self._write("security.json", {"findings": ["text"]})
        with self.assertRaises(ValueError):
            providers.load_result(self.dir / "security.json", "security")


class TestRecordedProvider(unittest.TestCase):
    """Fixture replay provider."""

    def test_lists_and_loads_fixtures(self):
        provider = providers.RecordedProvider(ROOT / "tests" / "fixtures" / "agents")
        ids = provider.agent_ids()
        self.assertIn("security", ids)
        result = provider.get("security")
        self.assertIn("findings", result)
        self.assertEqual(result["agent"], "security")


class TestLoadResult(unittest.TestCase):
    def test_accepts_utf8_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "phase_security.json"
            path.write_bytes(
                b"\xef\xbb\xbf" + json.dumps({"findings": []}).encode("utf-8")
            )
            result = providers.load_result(path, "security")
            self.assertEqual(result["agent"], "security")

    def test_rejects_non_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "phase_security.json"
            path.write_text("[1, 2]", encoding="utf-8")
            with self.assertRaises(ValueError):
                providers.load_result(path, "security")


if __name__ == "__main__":
    unittest.main()
