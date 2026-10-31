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
from tests import create_directory_link  # noqa: E402

TARGET = ROOT / "tests" / "dummy_repo"
FIXTURES = ROOT / "tests" / "fixtures" / "agents"


def run(argv):
    """Run the CLI in-process and return (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


class TestCreateDirectoryLink(unittest.TestCase):
    """Directory links must survive spaces and refuse cmd metacharacters."""

    def test_link_inside_a_path_with_spaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "space dir"
            (root / "inner dir").mkdir(parents=True)
            target = root / "target dir"
            target.mkdir()
            (target / "marker.txt").write_text("ok", encoding="utf-8")
            link = root / "inner dir" / "link dir"
            try:
                create_directory_link(link, target)
            except OSError as exc:
                self.skipTest("directory links unavailable: " + str(exc))
            self.assertTrue((link / "marker.txt").is_file())

    def test_cmd_metacharacters_are_rejected(self):
        for char in ('"', "&", "|", "<", ">", "^", "%"):
            with self.subTest(char=char):
                with self.assertRaises(OSError) as ctx:
                    create_directory_link(
                        Path("bad") / ("a" + char + "b"), Path("target")
                    )
                self.assertIn(repr(char), str(ctx.exception))

    def test_metacharacter_in_target_is_rejected(self):
        with self.assertRaises(OSError) as ctx:
            create_directory_link(Path("link"), Path("a&b"))
        self.assertIn("a&b", str(ctx.exception))


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

    def test_null_re_review_count_is_carried_forward_as_zero(self):
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
        self.assertEqual(data["re_review_count"], 0)

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
        self.assertEqual(data["re_review_count"], 0)

    def test_record_does_not_advance_completed_re_reviews(self):
        # An abandoned run must not count as a finished re-review.
        code, _, _ = run([
            "record", str(TARGET), "--out", str(self.cache),
            "--agents", "security",
        ])
        self.assertEqual(code, 0)
        state_path = self.cache / "ccr-state.json"
        data = json.loads(state_path.read_text(encoding="utf-8"))
        data["re_review_count"] = 4
        state_path.write_text(json.dumps(data), encoding="utf-8")
        code, _, _ = run([
            "record", str(TARGET), "--out", str(self.cache),
            "--agents", "security",
        ])
        self.assertEqual(code, 0)
        data = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(data["re_review_count"], 4)

    def test_archive_failure_exits_two(self):
        with mock.patch.object(
                cli, "_archive_results", side_effect=OSError("boom")):
            code, out, _ = run([
                "record", str(TARGET), "--out", str(self.cache),
                "--agents", "security",
            ])
        self.assertEqual(code, 2)
        self.assertIn("could not archive stale results", out)

    def test_archive_refuses_file_blocking_previous_results(self):
        (self.cache / "phase_security.json").write_text(
            '{"agent": "security", "findings": []}', encoding="utf-8"
        )
        base = self.cache / "previous-results"
        base.write_text("blocking file", encoding="utf-8")
        code, out, _ = run([
            "record", str(TARGET), "--out", str(self.cache),
            "--agents", "security",
        ])
        self.assertEqual(code, 2)
        self.assertIn("[ERROR] could not archive stale results", out)
        self.assertIn(str(base), out)
        self.assertTrue(base.is_file())
        self.assertTrue((self.cache / "phase_security.json").exists())

    def test_archive_name_retries_are_bounded(self):
        (self.cache / "previous-results").mkdir()
        (self.cache / "phase_security.json").write_text(
            "{}", encoding="utf-8"
        )

        def taken_mkdir(path, *args, **kwargs):
            raise FileExistsError("simulated permanent collision")

        with mock.patch.object(Path, "mkdir", taken_mkdir):
            with self.assertRaises(OSError) as ctx:
                cli._archive_results(self.cache)
        self.assertIn("no free archive name", str(ctx.exception))

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

    def test_record_refuses_junctioned_previous_results(self):
        target = Path(self.tmp.name) / "elsewhere"
        target.mkdir()
        base = self.cache / "previous-results"
        try:
            create_directory_link(base, target)
        except OSError as exc:
            self.skipTest("directory links unavailable: " + str(exc))
        (self.cache / "phase_security.json").write_text(
            '{"agent": "security", "findings": []}', encoding="utf-8"
        )
        code, out, _ = run([
            "record", str(TARGET), "--out", str(self.cache),
            "--agents", "security",
        ])
        self.assertEqual(code, 2)
        self.assertIn("[ERROR] could not archive stale results", out)
        self.assertEqual(list(target.iterdir()), [])

    def test_archive_rechecks_after_directory_creation(self):
        # Deterministic race: the parent is swapped for a link after the
        # pre-check, just before the archive directory is created.
        outside = Path(self.tmp.name) / "elsewhere"
        outside.mkdir()
        base = self.cache / "previous-results"
        base.mkdir()
        (self.cache / "phase_security.json").write_text(
            '{"agent": "security", "findings": []}', encoding="utf-8"
        )
        real_mkdir = Path.mkdir

        def racing_mkdir(path, *args, **kwargs):
            if path.parent == base and not cli._is_link_like(base):
                base.rmdir()
                try:
                    create_directory_link(base, outside)
                except OSError as exc:
                    self.skipTest("directory links unavailable: " + str(exc))
            return real_mkdir(path, *args, **kwargs)

        with mock.patch.object(Path, "mkdir", racing_mkdir):
            with self.assertRaises(OSError):
                cli._archive_results(self.cache)
        self.assertEqual(list(outside.rglob("*.json")), [])
        self.assertTrue((self.cache / "phase_security.json").exists())

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
        self.assertIn("tech_debt_hours must be a finite number", out)

    def test_non_finite_baseline_exits_two(self):
        bad = self.dir / "baseline.json"
        bad.write_text('{"tech_debt_hours": NaN}', encoding="utf-8")
        code, out, _ = run([
            "synthesize", "--in", str(FIXTURES), "--agents", "security",
            "--baseline", str(bad),
        ])
        self.assertEqual(code, 2)
        self.assertIn("tech_debt_hours must be a finite number", out)

    def test_huge_integer_baseline_exits_two(self):
        bad = self.dir / "baseline.json"
        bad.write_text(
            '{"tech_debt_hours": 1' + "0" * 400 + "}", encoding="utf-8"
        )
        code, out, _ = run([
            "synthesize", "--in", str(FIXTURES), "--agents", "security",
            "--baseline", str(bad),
        ])
        self.assertEqual(code, 2)
        self.assertIn("tech_debt_hours must be a finite number", out)

    def test_report_write_failure_exits_two(self):
        with mock.patch.object(
                cli.pipeline, "write_outputs",
                side_effect=OSError("bad output")):
            code, out, _ = run([
                "synthesize", "--in", str(FIXTURES), "--agents", "security",
                "--out", str(self.dir / "report"),
            ])
        self.assertEqual(code, 2)
        self.assertIn("could not write report", out)

    def test_report_encoding_failure_exits_two(self):
        error = UnicodeEncodeError("utf-8", "x", 0, 1, "surrogate")
        with mock.patch.object(
                cli.pipeline, "write_outputs", side_effect=error):
            code, out, _ = run([
                "synthesize", "--in", str(FIXTURES), "--agents", "security",
                "--out", str(self.dir / "report"),
            ])
        self.assertEqual(code, 2)
        self.assertIn("could not write report", out)

    def test_eval_runs_from_any_directory(self):
        old = os.getcwd()
        try:
            os.chdir(self.dir)
            code, out, err = run(["eval"])
        finally:
            os.chdir(old)
        self.assertEqual(code, 0, out + err)
        self.assertIn("[EVAL] coverage=100%", out)

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

    def test_validate_results_forces_manifest_domain(self):
        cache = self.dir / "cache"
        cache.mkdir()
        finding = {
            "finding": "[app.py:9] \u2014 repeated state update \u2192 "
                       "two writes for one event",
            "severity": "MEDIUM",
            "est_hours": 1,
            "da_verdict": "CONFIRMED",
        }
        (cache / "phase_security.json").write_text(json.dumps({
            "agent": "security",
            "findings": [dict(finding, domain="Architecture"), finding],
        }), encoding="utf-8")
        code, out, _ = run([
            "validate-results", "--in", str(cache), "--agents", "security",
            "--json",
        ])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["valid"], 1)

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


class TestCliReReviewBaseline(unittest.TestCase):
    """State's re_review_count must reach the report baseline snapshot."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.cache = self.dir / "cache"
        self.cache.mkdir()
        shutil.copyfile(
            FIXTURES / "security.json", self.cache / "phase_security.json"
        )

    def _write_state(self, **extra):
        data = {
            "target_dir": str(TARGET.resolve()),
            "current_phase": 1,
            "phase_gates": {},
            "agents_planned": ["security"],
        }
        data.update(extra)
        (self.cache / "ccr-state.json").write_text(
            json.dumps(data), encoding="utf-8"
        )

    def _synthesize_json(self):
        out = self.dir / "report"
        code, _, err = run([
            "synthesize", "--in", str(self.cache),
            "--format", "json", "--out", str(out),
        ])
        self.assertEqual(code, 0, err)
        return json.loads((self.dir / "report.json").read_text(
            encoding="utf-8"))

    def _state_count(self):
        data = json.loads((self.cache / "ccr-state.json").read_text(
            encoding="utf-8"))
        return data["re_review_count"]

    def test_state_re_review_count_reaches_baseline(self):
        self._write_state(re_review_count=2)
        report = self._synthesize_json()
        self.assertEqual(report["baseline"]["re_review_count"], 2)
        # The emitted report completes the re-review, so the next run sees 3.
        self.assertEqual(self._state_count(), 3)

    def test_rerun_on_identical_results_counts_once(self):
        self._write_state(re_review_count=2)
        self._synthesize_json()
        self._synthesize_json()
        # Same payload reviewed twice is one completed review, not two.
        self.assertEqual(self._state_count(), 3)

    def test_changed_results_advance_the_count_again(self):
        self._write_state(re_review_count=2)
        self._synthesize_json()
        path = self.cache / "phase_security.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["findings"].append({
            "finding": "[app.py:9] \u2014 unchecked index \u2192 crash on "
                       "empty list",
            "severity": "LOW",
            "est_hours": 1,
            "da_verdict": "CONFIRMED",
        })
        path.write_text(json.dumps(data), encoding="utf-8")
        self._synthesize_json()
        self.assertEqual(self._state_count(), 4)

    def test_failed_report_write_does_not_advance_count(self):
        self._write_state(re_review_count=2)
        with mock.patch.object(
                cli, "_emit_synthesis_output", side_effect=OSError("disk full")):
            code, out, _ = run([
                "synthesize", "--in", str(self.cache),
                "--format", "json", "--out", str(self.dir / "report"),
            ])
        self.assertEqual(code, 2)
        self.assertIn("could not write report", out)
        self.assertEqual(self._state_count(), 2)

    def test_absent_re_review_count_defaults_to_zero(self):
        self._write_state()
        report = self._synthesize_json()
        self.assertEqual(report["baseline"]["re_review_count"], 0)

    def test_unresolvable_cached_target_warns_instead_of_crashing(self):
        self._write_state(target_dir=str(self.dir / "loop"))
        real_resolve = Path.resolve

        def looping_resolve(path, *args, **kwargs):
            if path.name == "loop":
                raise OSError(40, "Too many levels of symbolic links")
            return real_resolve(path, *args, **kwargs)

        with mock.patch.object(Path, "resolve", looping_resolve):
            code, _, err = run([
                "synthesize", "--in", str(self.cache),
                "--format", "json", "--out", str(self.dir / "report"),
            ])
        self.assertEqual(code, 0)
        self.assertIn("cached facts belong to", err)

    def test_mismatched_target_drops_cached_re_review_count(self):
        # A foreign baseline must not inherit the count of a different target.
        self._write_state(
            target_dir=str(self.dir / "other-target"), re_review_count=2
        )
        out = self.dir / "report"
        code, _, err = run([
            "synthesize", "--in", str(self.cache), "--target", str(TARGET),
            "--format", "json", "--out", str(out),
        ])
        self.assertEqual(code, 0, err)
        report = json.loads((self.dir / "report.json").read_text(
            encoding="utf-8"))
        self.assertEqual(report["baseline"]["re_review_count"], 0)
        # A foreign target's counter must not advance either.
        self.assertEqual(self._state_count(), 2)

    def test_null_target_dir_is_treated_as_absent(self):
        self._write_state(target_dir=None)
        code, _, err = run([
            "synthesize", "--in", str(self.cache),
            "--format", "json", "--out", str(self.dir / "report"),
        ])
        self.assertEqual(code, 0, err)
        self.assertNotIn("Traceback", err)
        report = json.loads((self.dir / "report.json").read_text(
            encoding="utf-8"))
        # The state carries no facts, so the size block stays empty instead
        # of crashing on a null target.
        self.assertEqual(report["report"]["codebase_size"]["files"], 0)

    def test_counter_save_failure_still_emits_the_report(self):
        self._write_state(re_review_count=2)
        with mock.patch.object(
                cli.state.State, "save", side_effect=OSError("read-only")):
            code, _, err = run([
                "synthesize", "--in", str(self.cache),
                "--format", "json", "--out", str(self.dir / "report"),
            ])
        self.assertEqual(code, 0)
        self.assertIn("[WARN] could not update re-review counter", err)
        self.assertTrue((self.dir / "report.json").is_file())

    def test_concurrent_record_rewrite_survives_the_counter_update(self):
        # A `record` may rewrite the state while this run is synthesizing.
        # Saving the snapshot loaded at startup would drop the new plan.
        self._write_state(re_review_count=2)
        state_path = self.cache / "ccr-state.json"
        emit = cli._emit_synthesis_output

        def rewrite_then_emit(*args, **kwargs):
            data = json.loads(state_path.read_text(encoding="utf-8"))
            data["agents_planned"] = ["security", "architecture"]
            data["facts"] = {"files": 42, "languages": {"py": 1}}
            data["current_step"] = "phase2:awaiting_agent_results"
            state_path.write_text(json.dumps(data), encoding="utf-8")
            return emit(*args, **kwargs)

        with mock.patch.object(cli, "_emit_synthesis_output",
                               rewrite_then_emit):
            code, _, err = run([
                "synthesize", "--in", str(self.cache),
                "--format", "json", "--out", str(self.dir / "report"),
            ])
        self.assertEqual(code, 0, err)
        data = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(data["agents_planned"], ["security", "architecture"])
        self.assertEqual(data["facts"]["files"], 42)
        self.assertEqual(data["current_step"], "phase2:awaiting_agent_results")
        self.assertEqual(data["re_review_count"], 3)

    def test_concurrent_counter_change_builds_on_the_fresh_value(self):
        # Another run may bump the counter between this run's load and save;
        # `snapshot + 1` would overwrite that review. The saved value must be
        # the freshly loaded count plus one.
        self._write_state(re_review_count=2)
        state_path = self.cache / "ccr-state.json"
        emit = cli._emit_synthesis_output

        def bump_then_emit(*args, **kwargs):
            data = json.loads(state_path.read_text(encoding="utf-8"))
            data["re_review_count"] = 5
            state_path.write_text(json.dumps(data), encoding="utf-8")
            return emit(*args, **kwargs)

        with mock.patch.object(cli, "_emit_synthesis_output", bump_then_emit):
            code, _, err = run([
                "synthesize", "--in", str(self.cache),
                "--format", "json", "--out", str(self.dir / "report"),
            ])
        self.assertEqual(code, 0, err)
        self.assertEqual(self._state_count(), 6)

    def test_vanished_state_file_warns_without_failing_the_run(self):
        self._write_state(re_review_count=2)
        state_path = self.cache / "ccr-state.json"
        emit = cli._emit_synthesis_output

        def remove_then_emit(*args, **kwargs):
            state_path.unlink()
            return emit(*args, **kwargs)

        with mock.patch.object(cli, "_emit_synthesis_output",
                               remove_then_emit):
            code, _, err = run([
                "synthesize", "--in", str(self.cache),
                "--format", "json", "--out", str(self.dir / "report"),
            ])
        self.assertEqual(code, 0)
        self.assertIn("[WARN] could not update re-review counter", err)
        self.assertFalse(state_path.exists())


class TestPersistReviewCounter(unittest.TestCase):
    """A report may only be credited to the state it was synthesized for."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.state_path = self.dir / "ccr-state.json"
        self.cached = self._write_state(str(TARGET), count=2)

    def _write_state(self, target_dir, count=0):
        data = {
            "target_dir": target_dir,
            "current_phase": 1,
            "phase_gates": {},
            "agents_planned": ["security"],
            "re_review_count": count,
        }
        self.state_path.write_text(json.dumps(data), encoding="utf-8")
        return cli.state.State.load(self.state_path)

    def _count(self):
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        return data["re_review_count"]

    def test_matching_target_increments_and_returns_true(self):
        saved = cli._persist_review_counter(self.cached, "sig-a", str(TARGET))
        self.assertTrue(saved)
        self.assertEqual(self._count(), 3)

    def test_same_signature_twice_increments_only_once(self):
        cli._persist_review_counter(self.cached, "sig-a", str(TARGET))
        cli._persist_review_counter(self.cached, "sig-a", str(TARGET))
        self.assertEqual(self._count(), 3)

    def test_mismatched_target_leaves_the_counter_unchanged(self):
        # A concurrent `record` for another directory swapped the state; this
        # report's count and signature must not be credited to the new target.
        other = self.dir / "other-target"
        other.mkdir()
        err = io.StringIO()
        with redirect_stderr(err):
            saved = cli._persist_review_counter(
                self.cached, "sig-a", str(other))
        self.assertFalse(saved)
        self.assertIn("state now belongs to " + str(TARGET), err.getvalue())
        self.assertEqual(self._count(), 2)
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertNotIn("last_synth_signature", data)

    def test_missing_state_file_warns_and_returns_false(self):
        self.state_path.unlink()
        err = io.StringIO()
        with redirect_stderr(err):
            saved = cli._persist_review_counter(
                self.cached, "sig-a", str(TARGET))
        self.assertFalse(saved)
        self.assertIn("[WARN] could not update re-review counter",
                      err.getvalue())
        self.assertFalse(self.state_path.exists())


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
