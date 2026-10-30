"""Tests for ccr.cli: subcommands, exit codes, and output."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from ccr import cli

ROOT = Path(__file__).resolve().parent.parent
DUMMY = ROOT / "tests" / "dummy_repo"
FIXTURES = ROOT / "tests" / "fixtures" / "agents"
AGENTS = "architecture,code_quality,security,tech_debt,test_health,documentation,standards"


def run_cli(argv):
    """Run the CLI with stdout captured. Returns (code, output)."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = cli.main(argv)
    return code, buffer.getvalue()


class TestPlanCommand(unittest.TestCase):
    """plan subcommand."""

    def test_conflicting_targets_exit_two(self):
        code, output = run_cli(["plan", "ccr", "--target", "tests"])
        self.assertEqual(code, 2)
        self.assertIn("target given twice", output)

    def test_plan_human(self):
        code, output = run_cli(["plan", "--target", str(DUMMY)])
        self.assertEqual(code, 0)
        self.assertIn("[PLAN]", output)
        self.assertIn("architecture", output)

    def test_plan_positional_target(self):
        code, output = run_cli(["plan", str(DUMMY)])
        self.assertEqual(code, 0)
        self.assertIn("[PLAN]", output)

    def test_plan_json(self):
        code, output = run_cli(["plan", "--target", str(DUMMY), "--json"])
        self.assertEqual(code, 0)
        data = json.loads(output)
        self.assertEqual(data["target"], str(DUMMY.resolve()))
        self.assertIn("facts", data)

    def test_plan_quick(self):
        code, output = run_cli(
            ["plan", "--target", str(DUMMY), "--effort", "min"]
        )
        self.assertEqual(code, 0)
        self.assertIn("quick", output)
        self.assertIn("timeout=120s", output)

    def test_plan_bad_target(self):
        code, _ = run_cli(["plan", "--target", str(DUMMY / "nope")])
        self.assertEqual(code, 2)

    def test_plan_unknown_agent(self):
        code, output = run_cli(
            ["plan", "--target", str(DUMMY), "--agents", "ghost"]
        )
        self.assertEqual(code, 2)
        self.assertIn("unknown agent", output)

    def test_plan_rejects_nonpositive_max_files(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                cli.main([
                    "plan", "--target", str(DUMMY), "--max-files", "0",
                ])
        self.assertEqual(ctx.exception.code, 2)


class TestRecordCommand(unittest.TestCase):
    """record subcommand."""

    def test_record_writes_prompts_and_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, output = run_cli([
                "record", "--target", str(DUMMY), "--out", tmp,
                "--agents", "security,architecture",
            ])
            self.assertEqual(code, 0)
            self.assertIn("wrote 2 prompts", output)
            self.assertTrue((Path(tmp) / "phase_security.prompt.md").exists())
            state_path = Path(tmp) / "ccr-state.json"
            data = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertTrue(data["phase_gates"]["p1_discovery"])
            self.assertEqual(data["agents_planned"], ["architecture", "security"])

    def test_record_reuses_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_cli([
                "record", "--target", str(DUMMY), "--out", tmp,
                "--agents", "security",
            ])
            code, _ = run_cli([
                "record", "--target", str(DUMMY), "--out", tmp,
                "--agents", "security",
            ])
            self.assertEqual(code, 0)

    def test_record_archives_stale_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_cli([
                "record", "--target", str(DUMMY), "--out", tmp,
                "--agents", "security",
            ])
            result = Path(tmp) / "phase_security.json"
            result.write_text('{"findings": []}', encoding="utf-8")
            code, output = run_cli([
                "record", "--target", str(DUMMY), "--out", tmp,
                "--agents", "security",
            ])
            self.assertEqual(code, 0)
            self.assertFalse(result.exists())
            archived = list(
                (Path(tmp) / "previous-results").rglob("phase_security.json")
            )
            self.assertEqual(len(archived), 1)
            self.assertIn("archived 1", output)

    def test_record_updates_effort(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_cli([
                "record", "--target", str(DUMMY), "--out", tmp,
                "--agents", "security", "--effort", "max",
            ])
            run_cli([
                "record", "--target", str(DUMMY), "--out", tmp,
                "--agents", "security", "--effort", "min",
            ])
            state = json.loads(
                (Path(tmp) / "ccr-state.json").read_text(encoding="utf-8")
            )
            self.assertEqual(state["effort"], "min")

    def test_record_stores_discovery_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_cli([
                "record", "--target", str(DUMMY), "--out", tmp,
                "--agents", "security",
            ])
            state = json.loads(
                (Path(tmp) / "ccr-state.json").read_text(encoding="utf-8")
            )
            self.assertEqual(state["facts"]["files"], 9)


class TestSynthesizeCommand(unittest.TestCase):
    """synthesize subcommand."""

    def test_synthesize_to_stdout(self):
        code, output = run_cli([
            "synthesize", "--in", str(FIXTURES), "--agents", AGENTS,
        ])
        self.assertEqual(code, 0)
        self.assertIn("## Executive Summary", output)

    def test_synthesize_to_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "report")
            code, output = run_cli([
                "synthesize", "--in", str(FIXTURES), "--agents", AGENTS,
                "--out", out, "--format", "both",
            ])
            self.assertEqual(code, 0)
            self.assertTrue(Path(out + ".md").exists())
            self.assertTrue(Path(out + ".json").exists())
            self.assertIn("health=", output)

    def test_synthesize_missing_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, output = run_cli([
                "synthesize", "--in", tmp, "--agents", "security",
            ])
            self.assertEqual(code, 2)
            self.assertIn("no agent results", output)

    def test_synthesize_no_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, output = run_cli(["synthesize", "--in", tmp])
            self.assertEqual(code, 2)
            self.assertIn("no agent results", output)

    def test_agents_flag_strips_spaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_cli([
                "record", "--target", str(DUMMY), "--out", tmp,
                "--agents", "security,architecture",
            ])
            for agent in ("security", "architecture"):
                (Path(tmp) / ("phase_" + agent + ".json")).write_text(
                    json.dumps({"findings": []}), encoding="utf-8"
                )
            code, _ = run_cli([
                "synthesize", "--in", tmp,
                "--agents", "security, architecture",
            ])
            self.assertEqual(code, 0)

    def test_invalid_state_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "ccr-state.json").write_text(
                "{not json", encoding="utf-8"
            )
            code, output = run_cli(["synthesize", "--in", tmp])
            self.assertEqual(code, 2)
            self.assertIn("invalid state", output)

    def test_report_carries_discovery_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_cli([
                "record", "--target", str(DUMMY), "--out", tmp,
                "--agents", "security",
            ])
            (Path(tmp) / "phase_security.json").write_text(
                '{"findings": []}', encoding="utf-8"
            )
            out = str(Path(tmp) / "report")
            code, _ = run_cli([
                "synthesize", "--in", tmp, "--out", out, "--format", "json",
            ])
            self.assertEqual(code, 0)
            data = json.loads(
                Path(out).with_suffix(".json").read_text(encoding="utf-8")
            )
            self.assertEqual(data["report"]["codebase_size"]["files"], 9)


class TestCompletionGate(unittest.TestCase):
    """Partial runs are blocked unless --allow-partial is explicit."""

    def _prepare(self, tmp, effort="max", results=("security", "architecture")):
        run_cli([
            "record", "--target", str(DUMMY), "--out", tmp,
            "--effort", effort,
            "--agents", "security,architecture,test_health",
        ])
        for agent in results:
            (Path(tmp) / ("phase_" + agent + ".json")).write_text(
                json.dumps({"findings": []}), encoding="utf-8"
            )

    def test_full_mode_blocks_two_of_three(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._prepare(tmp)
            code, output = run_cli(["synthesize", "--in", tmp])
            self.assertEqual(code, 1)
            self.assertIn("insufficient agent coverage", output)

    def test_allow_partial_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._prepare(tmp)
            code, output = run_cli(
                ["synthesize", "--in", tmp, "--allow-partial"]
            )
            self.assertEqual(code, 0)
            self.assertIn("Completed: 2/3 agents", output)

    def test_quick_mode_two_of_three_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._prepare(tmp, effort="min")
            code, _ = run_cli(["synthesize", "--in", tmp])
            self.assertEqual(code, 0)

    def test_agents_flag_overrides_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._prepare(tmp, results=("security",))
            code, _ = run_cli([
                "synthesize", "--in", tmp, "--agents", "security",
            ])
            self.assertEqual(code, 0)


class TestEvalCommand(unittest.TestCase):
    """eval subcommand."""

    def test_eval_passes(self):
        code, output = run_cli(["eval"])
        self.assertEqual(code, 0)
        self.assertIn("coverage=100%", output)

    def test_eval_json(self):
        code, output = run_cli(["eval", "--json"])
        self.assertEqual(code, 0)
        data = json.loads(output)
        self.assertEqual(data["coverage"], 1.0)

    def test_eval_missing_expected(self):
        code, _ = run_cli(["eval", "--expected", "does-not-exist.json"])
        self.assertEqual(code, 2)


class TestParser(unittest.TestCase):
    """Global parser behaviour."""

    def test_version_exits_zero(self):
        with contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                cli.main(["--version"])
        self.assertEqual(ctx.exception.code, 0)

    def test_no_command_exits(self):
        with contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                cli.main([])
        self.assertEqual(ctx.exception.code, 2)


class TestResolvePlanned(unittest.TestCase):
    def test_from_agents(self):
        import argparse
        args = argparse.Namespace(agents="a,b", cache=".")
        cached = None
        self.assertEqual(cli._resolve_planned(args, cached), ["a", "b"])

    def test_empty_agents_string(self):
        import argparse
        args = argparse.Namespace(agents=", ,", cache=".")
        cached = None
        self.assertEqual(cli._resolve_planned(args, cached), [])

    def test_agents_flag_accepts_display_names(self):
        import argparse
        from ccr import manifest as manifest_mod
        args = argparse.Namespace(agents="Security,Architecture", cache=".")
        planned = cli._resolve_planned(
            args, None, manifest=manifest_mod.load()
        )
        self.assertEqual(planned, ["security", "architecture"])

    def test_agents_flag_accepts_parenthesized_name(self):
        import argparse
        from ccr import manifest as manifest_mod
        args = argparse.Namespace(
            agents="Process Quality (Karpathy Compliance)", cache="."
        )
        planned = cli._resolve_planned(
            args, None, manifest=manifest_mod.load()
        )
        self.assertEqual(planned, ["process_quality"])

    def test_agents_flag_dedupes_spellings(self):
        import argparse
        from ccr import manifest as manifest_mod
        args = argparse.Namespace(agents="security,Security", cache=".")
        planned = cli._resolve_planned(
            args, None, manifest=manifest_mod.load()
        )
        self.assertEqual(planned, ["security"])


class TestCheckCompletionGate(unittest.TestCase):
    def test_allow_partial(self):
        import argparse
        args = argparse.Namespace(allow_partial=True)
        self.assertIsNone(cli._check_completion_gate({}, "max", [], [], True, args))

    def test_gate_unknown(self):
        import argparse
        args = argparse.Namespace(allow_partial=False)
        self.assertIsNone(cli._check_completion_gate({}, "max", [], [], False, args))

    def test_success(self):
        import argparse
        orig = cli.pipeline.check_completion
        cli.pipeline.check_completion = lambda *a, **k: None
        try:
            args = argparse.Namespace(allow_partial=False)
            self.assertIsNone(cli._check_completion_gate({}, "max", ["a"], ["a"], True, args))
        finally:
            cli.pipeline.check_completion = orig

    def test_runtime_error(self):
        import argparse
        def boom(*a, **k):
            raise RuntimeError("boom")
        orig = cli.pipeline.check_completion
        cli.pipeline.check_completion = boom
        try:
            args = argparse.Namespace(allow_partial=False)
            exc = cli._check_completion_gate({}, "max", ["a"], [], True, args)
            self.assertIsInstance(exc, RuntimeError)
        finally:
            cli.pipeline.check_completion = orig


class TestLoadSynthesisResults(unittest.TestCase):
    def test_missing(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            import argparse
            args = argparse.Namespace(cache=tmp)
            with self.assertRaises(ValueError):
                cli._load_synthesis_results(args, ["nope"])


class TestEmitSynthesisOutput(unittest.TestCase):
    def test_stdout(self):
        import argparse
        from types import SimpleNamespace
        model = {
            "overall_health": "GREEN", "critical_issues": 0,
            "tech_debt_hours": 1.0, "agent_status": {"completed": 1, "total": 1},
        }
        args = SimpleNamespace(out=None, format="markdown")
        # render stub
        orig_render = cli.pipeline.render
        cli.pipeline.render = lambda m, f: {"markdown": "MD"}
        try:
            code = cli._emit_synthesis_output(model, args)
            self.assertEqual(code, 0)
        finally:
            cli.pipeline.render = orig_render


class TestPlannedFromCache(unittest.TestCase):
    def test_ignores_non_result_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            (cache / "security.json").write_text(
                json.dumps({"findings": []}), encoding="utf-8")
            (cache / "report.json").write_text(
                json.dumps({"report": {}}), encoding="utf-8")
            (cache / "ccr-state.json").write_text("{}", encoding="utf-8")
            self.assertEqual(cli._planned_from_cache(str(cache)), ["security"])

    def test_filters_report_json_with_valid_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            for name in ("security", "report-cli"):
                (cache / (name + ".json")).write_text(
                    json.dumps({"findings": []}), encoding="utf-8")
            self.assertEqual(
                cli._planned_from_cache(str(cache), valid_ids={"security"}),
                ["security"],
            )

    def test_accepts_bom_prefixed_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            payload = json.dumps({"findings": []}).encode("utf-8")
            (cache / "security.json").write_bytes(b"\xef\xbb\xbf" + payload)
            self.assertEqual(cli._planned_from_cache(str(cache)), ["security"])

    def test_accepts_phase_prefixed_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            (cache / "phase_security.json").write_text(
                json.dumps({"findings": []}), encoding="utf-8")
            self.assertEqual(cli._planned_from_cache(str(cache)), ["security"])


class TestValidateResults(unittest.TestCase):
    def test_reports_malformed(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "security.json").write_text(json.dumps({
                "findings": [
                    {"finding": "[a.py:1] \u2014 flaw \u2192 failure",
                     "severity": "LOW", "est_hours": 1},
                    {"finding": "no anchor", "severity": "LOW",
                     "est_hours": 1},
                ]
            }), encoding="utf-8")
            code, output = run_cli(["validate-results", "--in", tmp])
            self.assertEqual(code, 0)
            self.assertIn("security: 1 valid, 1 malformed", output)

    def test_malformed_over_threshold_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "security.json").write_text(json.dumps({
                "findings": [
                    {"finding": "no anchor", "severity": "LOW",
                     "est_hours": 1},
                    {"finding": "no anchor", "severity": "LOW",
                     "est_hours": 1},
                    {"finding": "no anchor", "severity": "LOW",
                     "est_hours": 1},
                    {"finding": "no anchor", "severity": "LOW",
                     "est_hours": 1},
                ]
            }), encoding="utf-8")
            code, output = run_cli(["validate-results", "--in", tmp])
            self.assertEqual(code, 1)
            self.assertIn("0 valid, 4 malformed", output)

    def test_clean_results_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "security.json").write_text(json.dumps({
                "findings": [
                    {"finding": "[a.py:1] \u2014 flaw \u2192 failure",
                     "severity": "LOW", "est_hours": 1},
                ]
            }), encoding="utf-8")
            code, output = run_cli(["validate-results", "--in", tmp])
            self.assertEqual(code, 0)
            self.assertIn("1 valid, 0 malformed", output)

    def test_no_results_exit_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, output = run_cli(["validate-results", "--in", tmp])
            self.assertEqual(code, 2)
            self.assertIn("no agent results", output)


class TestEvalExit(unittest.TestCase):
    """eval returns 1 when an expected issue goes unreported."""

    def test_unmatched_expected_issue_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            expected = Path(tmp) / "expected.json"
            expected.write_text(
                json.dumps(["no-such-issue-xyz"]), encoding="utf-8"
            )
            code, output = run_cli([
                "eval", "--fixtures", str(FIXTURES),
                "--expected", str(expected),
            ])
            self.assertEqual(code, 1)
            self.assertIn("missing: no-such-issue-xyz", output)


class TestModuleEntrypoint(unittest.TestCase):
    def test_python_dash_m_ccr(self):
        import runpy
        import sys
        from unittest import mock
        argv = ["ccr", "--help"]
        with mock.patch.object(sys, "argv", argv):
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    runpy.run_module("ccr", run_name="__main__")
        self.assertEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
