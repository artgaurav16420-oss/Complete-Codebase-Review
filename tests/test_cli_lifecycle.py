"""Lifecycle tests for ccr.cli: record resets, archiving, baseline, target."""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ccr import cli  # noqa: E402

TARGET = ROOT / "tests" / "dummy_repo"
FIXTURES = ROOT / "tests" / "fixtures" / "agents"


def run(argv):
    """Run the CLI in-process and return (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


class TestCliRecordLifecycle(unittest.TestCase):
    """record must start a clean run and archive every result layout."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = Path(self.tmp.name) / "cache"
        self.cache.mkdir()

    def test_second_record_resets_phase_and_completions(self):
        code, _, _ = run([
            "record", str(TARGET), "--out", str(self.cache),
            "--agents", "security,code_quality",
        ])
        self.assertEqual(code, 0)
        state_path = self.cache / "ccr-state.json"
        data = json.loads(state_path.read_text(encoding="utf-8"))
        data["current_phase"] = 5
        data["phase_gates"]["p5_pr_created"] = True
        data["agents_completed"] = ["security", "code_quality"]
        data["completed_count"] = 2
        state_path.write_text(json.dumps(data), encoding="utf-8")

        code, _, _ = run([
            "record", str(TARGET), "--out", str(self.cache),
            "--agents", "security,code_quality,architecture",
        ])
        self.assertEqual(code, 0)
        data = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(data["current_phase"], 1)
        self.assertFalse(data["phase_gates"]["p5_pr_created"])
        self.assertTrue(data["phase_gates"]["p1_discovery"])
        self.assertEqual(data["agents_completed"], [])
        self.assertEqual(data["completed_count"], 0)
        self.assertEqual(data["total_agents"], 3)
        self.assertEqual(data["current_step"], "phase2:awaiting_agent_results")

    def test_null_re_review_count_is_tolerated(self):
        code, _, _ = run([
            "record", str(TARGET), "--out", str(self.cache),
            "--agents", "security",
        ])
        self.assertEqual(code, 0)
        state_path = self.cache / "ccr-state.json"
        data = json.loads(state_path.read_text(encoding="utf-8"))
        data["re_review_count"] = None
        state_path.write_text(json.dumps(data), encoding="utf-8")
        code, _, _ = run([
            "record", str(TARGET), "--out", str(self.cache),
            "--agents", "security",
        ])
        self.assertEqual(code, 0)
        data = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(data["re_review_count"], 1)

    def test_non_numeric_re_review_count_is_normalized(self):
        code, _, _ = run([
            "record", str(TARGET), "--out", str(self.cache),
            "--agents", "security",
        ])
        self.assertEqual(code, 0)
        state_path = self.cache / "ccr-state.json"
        data = json.loads(state_path.read_text(encoding="utf-8"))
        data["re_review_count"] = "not-a-number"
        state_path.write_text(json.dumps(data), encoding="utf-8")
        code, _, _ = run([
            "record", str(TARGET), "--out", str(self.cache),
            "--agents", "security",
        ])
        self.assertEqual(code, 0)
        data = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(data["re_review_count"], 1)

    def test_archive_failure_exits_two(self):
        with mock.patch.object(
                cli, "_archive_results", side_effect=OSError("boom")):
            code, out, _ = run([
                "record", str(TARGET), "--out", str(self.cache),
                "--agents", "security",
            ])
        self.assertEqual(code, 2)
        self.assertIn("could not archive stale results", out)

    def test_archive_directory_creation_is_atomic(self):
        (self.cache / "phase_security.json").write_text(
            '{"agent": "security", "findings": []}', encoding="utf-8"
        )
        (self.cache / "previous-results").mkdir()
        real_mkdir = Path.mkdir
        calls = []

        def flaky_mkdir(path, *args, **kwargs):
            calls.append(path)
            if len(calls) == 1:
                raise FileExistsError("simulated concurrent record")
            return real_mkdir(path, *args, **kwargs)

        with mock.patch.object(Path, "mkdir", flaky_mkdir):
            written = cli._archive_results(self.cache)
        self.assertEqual(written, 1)
        dirs = list((self.cache / "previous-results").iterdir())
        self.assertEqual(len(dirs), 1)
        self.assertTrue(dirs[0].name.endswith("-1"))

    def test_archive_rolls_back_on_partial_move(self):
        for name in ("security", "architecture"):
            (self.cache / f"phase_{name}.json").write_text(
                "{}", encoding="utf-8")
        real_move = shutil.move
        calls = []

        def flaky_move(source, target):
            calls.append(source)
            if len(calls) == 2:
                raise OSError("simulated move failure")
            return real_move(source, target)

        with mock.patch.object(cli.shutil, "move", flaky_move):
            with self.assertRaises(OSError):
                cli._archive_results(self.cache)
        self.assertTrue((self.cache / "phase_security.json").exists())
        self.assertTrue((self.cache / "phase_architecture.json").exists())
        self.assertEqual(
            list((self.cache / "previous-results").iterdir()), []
        )

    def test_archive_refuses_symlinked_previous_results(self):
        target = Path(self.tmp.name) / "elsewhere"
        target.mkdir()
        base = self.cache / "previous-results"
        try:
            os.symlink(target, base, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("symlink creation unavailable: " + str(exc))
        (self.cache / "phase_security.json").write_text(
            '{"agent": "security", "findings": []}', encoding="utf-8"
        )
        with self.assertRaises(OSError):
            cli._archive_results(self.cache)
        self.assertEqual(list(target.iterdir()), [])

    def test_bare_agent_result_is_archived(self):
        result = self.cache / "security.json"
        result.write_text('{"agent": "security", "findings": []}',
                          encoding="utf-8")
        code, _, _ = run([
            "record", str(TARGET), "--out", str(self.cache),
            "--agents", "security",
        ])
        self.assertEqual(code, 0)
        self.assertFalse(result.exists())
        archived = list((self.cache / "previous-results").glob(
            "*/security.json"))
        self.assertEqual(len(archived), 1)

    def test_prompt_write_failure_keeps_stale_results(self):
        stale = self.cache / "phase_security.json"
        stale.write_text('{"agent": "security", "findings": []}',
                         encoding="utf-8")
        (self.cache / "phase_architecture.prompt.md").mkdir()
        code, out, _ = run([
            "record", str(TARGET), "--out", str(self.cache),
            "--agents", "security,architecture",
        ])
        self.assertEqual(code, 2)
        self.assertIn("[ERROR]", out)
        self.assertTrue(stale.exists())
        self.assertFalse((self.cache / "previous-results").exists())

    def test_archive_directory_names_collide_safely(self):
        class FixedDatetime:
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 10, 30, 8, 0, 0, tzinfo=timezone.utc)

        with mock.patch.object(cli, "datetime", FixedDatetime):
            for name in ("a", "b"):
                (self.cache / f"phase_{name}.json").write_text(
                    "{}", encoding="utf-8")
                cli._archive_results(self.cache)
        base = self.cache / "previous-results"
        self.assertTrue((base / "20261030-080000" / "phase_a.json").exists())
        self.assertTrue((base / "20261030-080000-1" / "phase_b.json").exists())


class TestCliSynthesizeOptions(unittest.TestCase):
    """--baseline and --target behaviour."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_baseline_drives_the_trend_line(self):
        baseline = self.dir / "baseline.json"
        baseline.write_text(json.dumps({"tech_debt_hours": 10}),
                            encoding="utf-8")
        out = self.dir / "report"
        code, _, _ = run([
            "synthesize", "--in", str(FIXTURES), "--agents", "security",
            "--baseline", str(baseline), "--target", str(TARGET),
            "--format", "json", "--out", str(out),
        ])
        self.assertEqual(code, 0)
        report = json.loads((self.dir / "report.json").read_text(
            encoding="utf-8"))
        self.assertTrue(report["tech_debt"]["trend"].startswith("10h -> "))

    def test_target_mismatch_drops_cached_facts(self):
        cache = self.dir / "cache"
        code, _, _ = run([
            "record", str(TARGET), "--out", str(cache), "--agents", "security",
        ])
        self.assertEqual(code, 0)
        shutil.copyfile(FIXTURES / "security.json",
                        cache / "phase_security.json")
        out = self.dir / "report"
        code, _, err = run([
            "synthesize", "--in", str(cache), "--target", str(ROOT),
            "--format", "json", "--out", str(out),
        ])
        self.assertEqual(code, 0)
        self.assertIn("cached facts belong to", err)
        report = json.loads((self.dir / "report.json").read_text(
            encoding="utf-8"))
        self.assertEqual(report["report"]["codebase_size"]["files"], 0)

    def test_invalid_baseline_exits_two(self):
        bad = self.dir / "baseline.json"
        bad.write_text("[]", encoding="utf-8")
        code, out, _ = run([
            "synthesize", "--in", str(FIXTURES), "--agents", "security",
            "--baseline", str(bad),
        ])
        self.assertEqual(code, 2)
        self.assertIn("[ERROR] invalid baseline", out)

    def test_non_numeric_baseline_exits_two(self):
        bad = self.dir / "baseline.json"
        bad.write_text(json.dumps({"tech_debt_hours": "10"}),
                       encoding="utf-8")
        code, out, _ = run([
            "synthesize", "--in", str(FIXTURES), "--agents", "security",
            "--baseline", str(bad),
        ])
        self.assertEqual(code, 2)
        self.assertIn("tech_debt_hours must be a number", out)

    def test_bom_baseline_is_accepted(self):
        baseline = self.dir / "baseline.json"
        baseline.write_bytes(
            b"\xef\xbb\xbf" + json.dumps({"tech_debt_hours": 10}).encode()
        )
        out = self.dir / "report"
        code, _, _ = run([
            "synthesize", "--in", str(FIXTURES), "--agents", "security",
            "--baseline", str(baseline), "--format", "json",
            "--out", str(out),
        ])
        self.assertEqual(code, 0)

    def test_validate_results_dedups_like_synthesize(self):
        cache = self.dir / "cache"
        cache.mkdir()
        finding = {
            "finding": "[app.py:7] \u2014 duplicated state update \u2192 "
                       "two writes for one event",
            "severity": "MEDIUM",
            "est_hours": 1,
            "da_verdict": "CONFIRMED",
        }
        (cache / "phase_security.json").write_text(json.dumps({
            "agent": "security",
            "findings": [finding, dict(finding)],
        }), encoding="utf-8")
        code, out, _ = run([
            "validate-results", "--in", str(cache), "--agents", "security",
            "--json",
        ])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["valid"], 1)
        self.assertEqual(data["malformed"], 0)


class TestCliVersionGuard(unittest.TestCase):
    """A broken manifest must not raise JSONDecodeError at import."""

    def test_truncated_manifest_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / "ccr", root / "ccr")
            (root / "ccr" / "pipeline.json").write_text(
                '{"version": ', encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-m", "ccr", "--version"],
                cwd=str(root), capture_output=True, text=True,
            )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("[ERROR]", proc.stdout)
        self.assertNotIn("JSONDecodeError", proc.stderr)

    def test_missing_manifest_loads_empty(self):
        import ccr
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(ccr, "_ROOT", Path(tmp)):
                self.assertEqual(ccr.load_pipeline(), {})

    def test_structurally_invalid_manifest_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / "ccr", root / "ccr")
            data = json.loads(
                (ROOT / "ccr" / "pipeline.json").read_text(encoding="utf-8")
            )
            data["thresholds"] = []
            (root / "ccr" / "pipeline.json").write_text(
                json.dumps(data), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-m", "ccr", "--version"],
                cwd=str(root), capture_output=True, text=True,
            )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("[ERROR]", proc.stdout)
        self.assertNotIn("Traceback", proc.stderr)

    def test_invalid_manifest_loads_empty(self):
        import ccr
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "pipeline.json").write_text("{", encoding="utf-8")
            with mock.patch.object(ccr, "_ROOT", Path(tmp)):
                self.assertEqual(ccr.load_pipeline(), {})

    def test_structurally_invalid_manifest_loads_empty(self):
        import ccr
        data = json.loads(
            (ROOT / "ccr" / "pipeline.json").read_text(encoding="utf-8")
        )
        data["thresholds"] = []
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "pipeline.json").write_text(
                json.dumps(data), encoding="utf-8")
            with mock.patch.object(ccr, "_ROOT", Path(tmp)):
                self.assertEqual(ccr.load_pipeline(), {})


if __name__ == "__main__":
    unittest.main()
