"""Tests for ccr.state: persistence, gates, and resume."""

import json
import tempfile
import unittest
from pathlib import Path

from ccr import manifest as manifest_mod
from ccr import state


class TestStateLifecycle(unittest.TestCase):
    """Create, save, and reload state."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "nested" / "ccr-state.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_writes_file(self):
        state.State.create(self.path, self.tmp.name)
        self.assertTrue(self.path.exists())
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["current_phase"], 1)
        self.assertEqual(data["effort"], "max")

    def test_roundtrip(self):
        created = state.State.create(self.path, self.tmp.name)
        created.set_step("phase1:discovery")
        loaded = state.State.load(self.path)
        self.assertEqual(loaded.data["current_step"], "phase1:discovery")

    def test_missing_file_returns_none(self):
        self.assertIsNone(state.State.load(self.path))

    def test_no_temp_file_left_behind(self):
        state.State.create(self.path, self.tmp.name)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_corrupt_state_rejected(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('{"current_phase": 9}', encoding="utf-8")
        with self.assertRaises(ValueError):
            state.State.load(self.path)


class TestGates(unittest.TestCase):
    """Phase and gate guards."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "ccr-state.json"
        self.state = state.State.create(self.path, self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_advance_without_discovery_raises(self):
        with self.assertRaises(ValueError):
            self.state.advance(2)

    def test_advance_after_gate(self):
        self.state.set_gate("p1_discovery", True)
        self.state.advance(2)
        self.assertEqual(self.state.data["current_phase"], 2)

    def test_cannot_skip_phase(self):
        self.state.set_gate("p1_discovery", True)
        with self.assertRaises(ValueError):
            self.state.advance(3)

    def test_invalid_phase(self):
        with self.assertRaises(ValueError):
            self.state.advance(9)

    def test_unknown_gate(self):
        with self.assertRaises(ValueError):
            self.state.set_gate("p9_done")

    def test_gate_roundtrip(self):
        self.state.set_gate("p5_tests_pass", True)
        loaded = state.State.load(self.path)
        self.assertTrue(loaded.data["phase_gates"]["p5_tests_pass"])


class TestAgents(unittest.TestCase):
    """Agent accounting and thresholds."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = state.State.create(
            Path(self.tmp.name) / "ccr-state.json", self.tmp.name
        )
        self.state.plan_agents(["security", "architecture", "documentation"])
        self.manifest = manifest_mod.load()

    def tearDown(self):
        self.tmp.cleanup()

    def test_record_requires_planned_agent(self):
        with self.assertRaises(ValueError):
            self.state.record_agent("ghost")

    def test_invalid_status(self):
        with self.assertRaises(ValueError):
            self.state.record_agent("security", status="maybe")

    def test_completed_count(self):
        self.state.record_agent("security")
        self.state.record_agent("architecture")
        self.assertEqual(self.state.data["completed_count"], 2)
        self.assertAlmostEqual(self.state.completion_ratio(), 2 / 3)

    def test_failed_moves_agent(self):
        self.state.record_agent("security")
        self.state.record_agent("security", status="failed")
        self.assertEqual(self.state.data["agents_completed"], [])
        self.assertEqual(self.state.data["agents_failed"], ["security"])

    def test_threshold_pass(self):
        for agent_id in ("security", "architecture", "documentation"):
            self.state.record_agent(agent_id)
        self.assertTrue(self.state.threshold_passed(self.manifest))

    def test_threshold_fail(self):
        self.state.record_agent("security")
        self.assertFalse(self.state.threshold_passed(self.manifest))

    def test_merge_resume_finds_disk_results(self):
        cache = Path(self.tmp.name) / "cache"
        cache.mkdir()
        (cache / "phase_security.json").write_text("{}", encoding="utf-8")
        drift = state.merge_resume(self.state, cache)
        self.assertEqual(drift, ["security"])

    def test_merge_resume_missing_dir(self):
        self.assertEqual(
            state.merge_resume(self.state, Path(self.tmp.name) / "nope"), []
        )


if __name__ == "__main__":
    unittest.main()
