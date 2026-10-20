"""Tests for ccr.discovery: facts, agent selection, and planning."""

import tempfile
import unittest
from pathlib import Path

from ccr import discovery
from ccr import manifest as manifest_mod

ROOT = Path(__file__).resolve().parent.parent
DUMMY = ROOT / "tests" / "dummy_repo"


class TestDiscover(unittest.TestCase):
    """Discovery facts for the dummy repository."""

    @classmethod
    def setUpClass(cls):
        cls.facts = discovery.discover(DUMMY)

    def test_counts_files(self):
        self.assertEqual(self.facts["files"], 9)
        self.assertEqual(self.facts["code_files"], 9)

    def test_detects_python(self):
        self.assertEqual(self.facts["languages"], {"Python": 9})

    def test_detects_entry_point(self):
        self.assertIn("app.py", self.facts["entry_points"])

    def test_detects_tests(self):
        self.assertEqual(self.facts["test_files"], 1)

    def test_no_false_tooling(self):
        self.assertEqual(self.facts["ci"], [])
        self.assertEqual(self.facts["containers"], [])
        self.assertEqual(self.facts["dependency_manifests"], [])

    def test_target_is_resolved(self):
        self.assertTrue(self.facts["target"].endswith("dummy_repo"))

    def test_rejects_file_target(self):
        with self.assertRaises(ValueError):
            discovery.discover(DUMMY / "app.py")

    def test_max_files_truncates(self):
        facts = discovery.discover(DUMMY, max_files=3)
        self.assertEqual(facts["files"], 3)
        self.assertTrue(facts["truncated"])

    def test_max_files_zero_or_negative_raises(self):
        for value in (0, -1):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    discovery.discover(DUMMY, max_files=value)

    def test_files_in_tests_dir_count_as_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests").mkdir()
            (root / "tests" / "helpers.py").write_text("x = 1\n", encoding="utf-8")
            facts = discovery.discover(root)
            self.assertEqual(facts["test_files"], 1)

    def test_ignores_vendor_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
            for ignored in ("node_modules", ".git", "__pycache__"):
                (root / ignored).mkdir()
                (root / ignored / "b.py").write_text("y = 2\n", encoding="utf-8")
            facts = discovery.discover(root)
            self.assertEqual(facts["files"], 1)


class TestActiveAgents(unittest.TestCase):
    """Dimension heuristics select the right agents."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = manifest_mod.load()

    def test_base_set_without_signals(self):
        active = discovery.active_agents(self.manifest, {})
        self.assertEqual(len(active), 7)
        self.assertNotIn("test_health", active)
        self.assertIn("process_quality", active)

    def test_all_signals_select_all_agents(self):
        facts = {
            "test_files": 3, "dependency_manifests": ["pyproject.toml"],
            "ci": [".github/workflows/ci.yml"], "database": ["migrations"],
            "ui_files": 2, "containers": ["Dockerfile"], "code_files": 40,
        }
        active = discovery.active_agents(self.manifest, facts)
        self.assertEqual(len(active), 14)

    def test_manifest_order_is_preserved(self):
        facts = {"test_files": 1, "ci": ["x.yml"]}
        active = discovery.active_agents(self.manifest, facts)
        order = [a["id"] for a in self.manifest["agents"]]
        self.assertEqual(active, [a for a in order if a in active])


class TestSelectAgents(unittest.TestCase):
    """Selection precedence: override > quick > dimensions."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = manifest_mod.load()
        cls.facts = discovery.discover(DUMMY)

    def test_quick_mode(self):
        agents = discovery.select_agents(self.manifest, self.facts, effort="min")
        self.assertEqual(agents, ["architecture", "code_quality", "security"])

    def test_override_by_id(self):
        agents = discovery.select_agents(
            self.manifest, self.facts, override="security,architecture"
        )
        self.assertEqual(agents, ["architecture", "security"])

    def test_override_by_report_name(self):
        agents = discovery.select_agents(
            self.manifest, self.facts, override="Code Quality"
        )
        self.assertEqual(agents, ["code_quality"])

    def test_override_beats_quick_mode(self):
        agents = discovery.select_agents(
            self.manifest, self.facts, effort="min", override="documentation"
        )
        self.assertEqual(agents, ["documentation"])

    def test_unknown_agent_raises(self):
        with self.assertRaises(ValueError):
            discovery.select_agents(self.manifest, self.facts, override="ghost")

    def test_invalid_effort_raises(self):
        with self.assertRaises(ValueError):
            discovery.select_agents(self.manifest, self.facts, effort="medium")


class TestPlan(unittest.TestCase):
    """Plan assembly."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = manifest_mod.load()

    def test_full_plan_timeout(self):
        plan = discovery.plan(self.manifest, DUMMY)
        self.assertEqual(plan["timeout_sec"], 900)
        self.assertFalse(plan["quick_mode"])
        self.assertEqual(len(plan["agents"]), 8)

    def test_quick_plan_timeout(self):
        plan = discovery.plan(self.manifest, DUMMY, effort="min")
        self.assertEqual(plan["timeout_sec"], 120)
        self.assertTrue(plan["quick_mode"])
        self.assertEqual(len(plan["agent_names"]), 3)


if __name__ == "__main__":
    unittest.main()
