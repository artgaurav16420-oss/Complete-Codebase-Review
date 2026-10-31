"""Tests for ccr.discovery: facts, agent selection, and planning."""

import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ccr import discovery
from ccr import manifest as manifest_mod
from tests import create_directory_link

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

    def test_ci_directory_named_like_a_workflow_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("print(1)\n", encoding="utf-8")
            workflows = root / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "ci.yml").write_text("name: x\n", encoding="utf-8")
            (workflows / "archive.yml").mkdir()
            facts = discovery.discover(str(root))
            self.assertEqual(facts["ci"], [".github/workflows/ci.yml"])

    def test_db_markers_in_service_subdirectory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "server" / "prisma").mkdir(parents=True)
            (root / "server" / "prisma" / "schema.prisma").write_text(
                "datasource db {}\n", encoding="utf-8"
            )
            (root / "server" / "migrations").mkdir()
            (root / "server" / "migrations" / "001_init.sql").write_text(
                "create table t (id int);\n", encoding="utf-8"
            )
            facts = discovery.discover(str(root))
        self.assertEqual(facts["database"], ["migrations", "prisma"])

    def test_db_scan_stops_at_the_depth_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "apps" / "api" / "prisma").mkdir(parents=True)
            (root / "a" / "b" / "c" / "migrations").mkdir(parents=True)
            facts = discovery.discover(str(root))
        self.assertEqual(facts["database"], ["prisma"])

    def test_linked_migrations_directory_is_not_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            outside = Path(tmp) / "outside"
            (outside / "migrations").mkdir(parents=True)
            (outside / "migrations" / "001_init.sql").write_text(
                "create table t (id int);\n", encoding="utf-8"
            )
            try:
                create_directory_link(root / "migrations", outside / "migrations")
            except OSError as exc:
                self.skipTest("directory links unavailable: " + str(exc))
            facts = discovery.discover(str(root))
        self.assertEqual(facts["database"], [])

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

    def test_renamed_dimension_agent_fails_loudly(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["agents"] = [
            a for a in manifest["agents"] if a["id"] != "test_health"
        ]
        with self.assertRaises(ValueError) as ctx:
            discovery.active_agents(manifest, {"test_files": 1})
        self.assertIn("test_health", str(ctx.exception))

    def test_override_tolerates_a_trailing_comma(self):
        manifest = manifest_mod.load()
        chosen = discovery.select_agents(
            manifest, {}, override="security,"
        )
        self.assertEqual(chosen, ["security"])

    def test_override_with_no_ids_fails_loudly(self):
        manifest = manifest_mod.load()
        with self.assertRaises(ValueError) as ctx:
            discovery.select_agents(manifest, {}, override=", ,")
        self.assertIn("no agent ids", str(ctx.exception))

    def test_unreadable_nested_directory_raises(self):
        def fake_walk(path, onerror=None):
            if onerror is not None:
                onerror(OSError("denied"))
            return iter(())

        with mock.patch.object(discovery.os, "walk", fake_walk):
            with self.assertRaises(ValueError) as ctx:
                discovery.discover(str(DUMMY))
        self.assertIn("cannot scan target directory", str(ctx.exception))

    def test_id_wins_over_an_earlier_agents_display_name(self):
        manifest = copy.deepcopy(manifest_mod.load())
        manifest["agents"][0]["name"] = manifest["agents"][1]["id"]
        resolved = discovery.resolve_agent(
            manifest, manifest["agents"][1]["id"]
        )
        self.assertEqual(resolved, manifest["agents"][1]["id"])

    def test_symlinked_ci_directory_is_not_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("print(1)\n", encoding="utf-8")
            outside = root / "outside"
            outside.mkdir()
            (outside / "ci.yml").write_text("name: x\n", encoding="utf-8")
            (root / ".github").mkdir()
            link = root / ".github" / "workflows"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation needs privilege here")
            facts = discovery.discover(str(root))
            self.assertEqual(facts["ci"], [])

    def test_symlinked_ci_parent_is_not_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("print(1)\n", encoding="utf-8")
            outside = root / "outside"
            (outside / "workflows").mkdir(parents=True)
            (outside / "workflows" / "ci.yml").write_text(
                "name: x\n", encoding="utf-8"
            )
            try:
                (root / ".github").symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation needs privilege here")
            facts = discovery.discover(str(root))
            self.assertEqual(facts["ci"], [])

    def test_ci_tree_is_skipped_when_a_component_is_a_reparse_point(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("print(1)\n", encoding="utf-8")
            workflows = root / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "ci.yml").write_text("name: x\n", encoding="utf-8")
            with mock.patch.object(
                discovery, "_is_reparse_dir", return_value=True
            ):
                facts = discovery.discover(str(root))
            self.assertEqual(facts["ci"], [])

    def test_symlinked_ci_file_is_not_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("print(1)\n", encoding="utf-8")
            (root / "outside.yml").write_text("name: x\n", encoding="utf-8")
            (root / ".github").mkdir()
            try:
                (root / ".github" / "workflows").symlink_to(
                    root / "outside.yml"
                )
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation needs privilege here")
            facts = discovery.discover(str(root))
            self.assertEqual(facts["ci"], [])

    def test_symlinked_workflow_file_is_not_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("print(1)\n", encoding="utf-8")
            (root / "outside.yml").write_text("name: x\n", encoding="utf-8")
            workflows = root / ".github" / "workflows"
            workflows.mkdir(parents=True)
            try:
                (workflows / "linked.yml").symlink_to(root / "outside.yml")
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation needs privilege here")
            facts = discovery.discover(str(root))
            self.assertEqual(facts["ci"], [])


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

    def test_full_plan_timeout_follows_env_var(self):
        with mock.patch.dict(
                os.environ, {"CODE_REVIEW_TIMEOUT_SEC": "1800"}):
            plan = discovery.plan(self.manifest, DUMMY)
        self.assertEqual(plan["timeout_sec"], 1800)

    def test_top_dirs_excludes_synthetic_root(self):
        plan = discovery.plan(self.manifest, DUMMY)
        self.assertNotIn(".", plan["facts"]["top_dirs"])


class TestProcessFile(unittest.TestCase):
    def test_updates_state(self):
        import tempfile, os
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root / "main.py"
            f.write_text("x", encoding="utf-8")
            state = {
                "files": 0, "total_bytes": 0, "languages": {},
                "top_dirs": {}, "dependency_manifests": [], "containers": [],
                "entry_points": [], "ui_files": 0, "test_files": 0,
            }
            discovery._process_file(f, Path("."), "main.py", f.stat().st_size, state)
            self.assertEqual(state["files"], 1)
            self.assertEqual(state["languages"].get("Python"), 1)
            self.assertNotIn(".", state["top_dirs"])


class TestUiFileClassification(unittest.TestCase):
    def _state(self):
        return {
            "files": 0, "total_bytes": 0, "languages": {},
            "top_dirs": {}, "dependency_manifests": [], "containers": [],
            "entry_points": [], "ui_files": 0, "test_files": 0,
        }

    def test_docs_markup_is_not_ui(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "style.css"
            f.write_text("body{}", encoding="utf-8")
            state = self._state()
            discovery._process_file(f, Path("docs"), "style.css", 7, state)
            self.assertEqual(state["ui_files"], 0)

    def test_app_markup_is_ui(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "app.css"
            f.write_text("body{}", encoding="utf-8")
            state = self._state()
            discovery._process_file(f, Path("src"), "app.css", 7, state)
            self.assertEqual(state["ui_files"], 1)

    def test_theme_under_src_is_ui(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "app.css"
            f.write_text("body{}", encoding="utf-8")
            state = self._state()
            discovery._process_file(
                f, Path("src") / "theme", "app.css", 7, state
            )
            self.assertEqual(state["ui_files"], 1)


class TestScanTree(unittest.TestCase):
    def test_limit_one(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i in range(3):
                (root / ("f%d.txt" % i)).write_text("x", encoding="utf-8")
            state = {
                "files": 0, "total_bytes": 0, "languages": {},
                "top_dirs": {}, "dependency_manifests": [], "containers": [],
                "entry_points": [], "ui_files": 0, "test_files": 0,
            }
            truncated = discovery._scan_tree(root, 1, state)
            self.assertTrue(truncated)
            self.assertEqual(state["files"], 1)

    def test_unlimited(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i in range(3):
                (root / ("f%d.txt" % i)).write_text("x", encoding="utf-8")
            state = {
                "files": 0, "total_bytes": 0, "languages": {},
                "top_dirs": {}, "dependency_manifests": [], "containers": [],
                "entry_points": [], "ui_files": 0, "test_files": 0,
            }
            truncated = discovery._scan_tree(root, 0, state)
            self.assertFalse(truncated)
            self.assertEqual(state["files"], 3)


if __name__ == "__main__":
    unittest.main()
