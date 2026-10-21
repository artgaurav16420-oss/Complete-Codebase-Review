"""Characterization tests for pipeline.synthesize (golden model output)."""

import json
from pathlib import Path

import unittest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"

import sys
sys.path.insert(0, str(ROOT))
from ccr import manifest, pipeline, providers


class TestCharacterization(unittest.TestCase):
    def _check(self, fixture_dir, golden_name):
        m = manifest.load()
        rp = providers.RecordedProvider(fixture_dir)
        ids = rp.agent_ids()
        results = providers.load_results(fixture_dir, ids, required=True)
        model = pipeline.synthesize(
            m, results, ids, target=".", facts={}, baseline=None,
            timestamp="2026-01-01T00:00:00",
        )
        actual = json.dumps(model, sort_keys=True, indent=2, ensure_ascii=False)
        golden_path = FIXTURES / "golden" / golden_name
        self.assertTrue(golden_path.exists(), "missing golden: " + str(golden_path))
        expected = golden_path.read_text(encoding="utf-8")
        self.assertEqual(actual, expected)

    def test_agents_golden(self):
        self._check(FIXTURES / "agents", "agents.json")

    def test_organizer_golden(self):
        self._check(FIXTURES / "organizer" / "agents", "organizer.json")


if __name__ == "__main__":
    unittest.main()
