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


if __name__ == "__main__":
    unittest.main()
