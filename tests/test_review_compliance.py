"""Compliance tests for skills/review/SKILL.md.

Checks structural, content, decision, validation, output, and
incremental review requirements against the review SKILL.md file.
Uses unittest as the canonical test framework (see ADR-003).

Usage:
    python tests/test_review_compliance.py
"""
import os
import re
import unittest


_REVIEW_SEVERITY_LEVELS = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]

_REVIEW_DECISIONS = ["APPROVE", "REQUEST CHANGES", "BLOCK"]

_REVIEW_REQUIRED_SECTIONS = [
    "## Phase 1",
    "## Phase 1.5",
    "## Phase 1.6",
    "## Phase 2",
    "## Phase 3",
    "## Edge Cases",
    "## Cleanup",
]

def _load_review_skill():
    """Load skills/review/SKILL.md content."""
    skill_path = os.path.join(
        os.path.dirname(__file__), "..", "skills", "review", "SKILL.md"
    )
    with open(skill_path, "r", encoding="utf-8") as f:
        return skill_path, f.read()


# --- unittest.TestCase wrappers ---


class _BaseReviewComplianceTest(unittest.TestCase):
    """Base class: loads review SKILL.md content once per class."""

    @classmethod
    def setUpClass(cls):
        cls.skill_path, cls.content = _load_review_skill()


class TestStructural(_BaseReviewComplianceTest):
    """Structural checks: YAML frontmatter, required sections, metadata."""

    def test_skill_md_exists_on_disk(self):
        self.assertTrue(os.path.exists(self.skill_path))

    def test_yaml_frontmatter_delimiters(self):
        self.assertIsNotNone(re.search(r"(?s)^---\r?\n.+\r?\n---", self.content))

    def test_frontmatter_name(self):
        self.assertIsNotNone(re.search(r"(?m)^name:\s*review", self.content))

    def test_frontmatter_description(self):
        self.assertIn("description:", self.content)

    def test_frontmatter_version(self):
        self.assertIsNotNone(re.search(r"(?m)^version:\s*\S+", self.content))

    def test_frontmatter_allowed_tools(self):
        self.assertIn("allowed-tools:", self.content)

    def test_frontmatter_argument_hint(self):
        self.assertIn("argument-hint:", self.content)

    def test_required_sections_present(self):
        for section in _REVIEW_REQUIRED_SECTIONS:
            with self.subTest(section=section):
                self.assertIn(section, self.content)

    def test_overview_section(self):
        self.assertIn("## Overview", self.content)

    def test_mode_selection_section(self):
        self.assertIn("## Mode Selection", self.content)

    def test_phase_35_section(self):
        self.assertIn("## Phase 3.5", self.content)

    def test_phase_4_section(self):
        self.assertIn("## Phase 4", self.content)


class TestSeverityLevels(_BaseReviewComplianceTest):
    """Severity levels: CRITICAL, HIGH, MEDIUM, LOW defined with meanings."""

    def test_all_severity_levels_defined(self):
        for level in _REVIEW_SEVERITY_LEVELS:
            with self.subTest(level=level):
                self.assertIn(level, self.content)

    def test_critical_is_security_or_data_loss(self):
        self.assertRegex(
            self.content,
            r"CRITICAL.*[Ss]ecurity vulnerability.*data loss",
        )

    def test_high_is_bug_or_logic_error(self):
        self.assertRegex(
            self.content,
            r"HIGH.*[Bb]ug.*logic error",
        )

    def test_medium_is_code_quality(self):
        self.assertRegex(
            self.content,
            r"MEDIUM.*[Cc]ode quality",
        )

    def test_low_is_style_or_suggestion(self):
        self.assertRegex(
            self.content,
            r"LOW.*[Ss]tyle nit.*suggestion",
        )

    def test_severity_actions_defined(self):
        self.assertIn("Must fix before merge", self.content)
        self.assertIn("Should fix before merge", self.content)
        self.assertIn("Fix recommended", self.content)
        self.assertIn("Optional", self.content)


class TestDecisionMatrix(_BaseReviewComplianceTest):
    """Decision matrix: APPROVE, REQUEST CHANGES, BLOCK."""

    def test_all_decisions_present(self):
        for decision in _REVIEW_DECISIONS:
            with self.subTest(decision=decision):
                self.assertIn(decision, self.content)

    def test_approve_condition_zero_critical_high(self):
        self.assertRegex(
            self.content,
            r"Zero CRITICAL/HIGH.*validation passes.*APPROVE",
        )

    def test_approve_with_comments_condition(self):
        self.assertIn("APPROVE with comments", self.content)
        self.assertIn("Only MEDIUM/LOW", self.content)

    def test_request_changes_condition(self):
        self.assertIn("REQUEST CHANGES", self.content)
        self.assertIn("Any HIGH or validation failures", self.content)

    def test_block_condition(self):
        self.assertIn("BLOCK", self.content)
        self.assertIn("Any CRITICAL", self.content)
        self.assertIn("must fix before merge", self.content)


class TestValidationCommands(_BaseReviewComplianceTest):
    """Validation commands table for each detected project type."""

    def test_validation_commands_table(self):
        self.assertIn("### Validation Commands", self.content)

    def test_node_ts_commands(self):
        self.assertIn("npm run typecheck", self.content)
        self.assertIn("npx tsc --noEmit", self.content)
        self.assertIn("npm run lint", self.content)
        self.assertIn("npm test", self.content)

    def test_rust_commands(self):
        self.assertIn("cargo clippy", self.content)
        self.assertIn("cargo test", self.content)
        self.assertIn("cargo build", self.content)

    def test_go_commands(self):
        self.assertIn("go vet ./...", self.content)
        self.assertIn("go test ./...", self.content)
        self.assertIn("go build ./...", self.content)

    def test_python_commands(self):
        self.assertIn("python -m pytest", self.content)
        self.assertIn("python -m unittest discover", self.content)

    def test_fallback_commands(self):
        self.assertIn("Fallback", self.content)
        self.assertIn("make test", self.content)

    def test_stdout_stderr_capture(self):
        self.assertIn("2>&1", self.content)


class TestJsonOutput(_BaseReviewComplianceTest):
    """JSON output structure: findings, validation_results, decision."""

    def test_json_output_section(self):
        self.assertIn("JSON Output", self.content)

    def test_findings_array(self):
        self.assertIn('"findings"', self.content)
        self.assertIn('"id"', self.content)
        self.assertIn('"severity"', self.content)
        self.assertIn('"title"', self.content)
        self.assertIn('"file"', self.content)
        self.assertIn('"line"', self.content)
        self.assertIn('"description"', self.content)
        self.assertIn('"suggested_fix"', self.content)

    def test_validation_results_object(self):
        self.assertIn('"validation_results"', self.content)
        self.assertIn('"typecheck"', self.content)
        self.assertIn('"lint"', self.content)
        self.assertIn('"tests"', self.content)
        self.assertIn('"build"', self.content)

    def test_decision_in_json(self):
        self.assertIn('"decision"', self.content)

    def test_counts_in_json(self):
        self.assertIn('"total_findings"', self.content)
        self.assertIn('"critical_count"', self.content)
        self.assertIn('"high_count"', self.content)
        self.assertIn('"medium_count"', self.content)
        self.assertIn('"low_count"', self.content)

    def test_files_reviewed_in_json(self):
        self.assertIn('"files_reviewed"', self.content)


class TestNewFeatures(_BaseReviewComplianceTest):
    """New features: Phase 1.6, cross-platform fallback, incremental tracking,
    --format, --chunk, --force-full flags."""

    def test_phase_16_large_pr_handling(self):
        self.assertIn("## Phase 1.6", self.content)
        self.assertIn("Large PR Handling", self.content)

    def test_phase_16_threshold(self):
        self.assertIn("50 changed files", self.content)
        self.assertIn("30,000 tokens", self.content)

    def test_phase_16_chunking_steps(self):
        self.assertIn("Detect", self.content)
        self.assertIn("Chunk", self.content)
        self.assertIn("Prioritize", self.content)
        self.assertIn("Iterate", self.content)
        self.assertIn("Warn", self.content)

    def test_cross_platform_fallback_logic(self):
        self.assertIn("Cross-Platform Fallback Logic", self.content)

    def test_cross_platform_platform_detection(self):
        self.assertIn("PowerShell", self.content)
        self.assertIn("Bash/Unix", self.content)
        self.assertIn("$PSVersionTable.PSEdition", self.content)
        self.assertIn("$BASH_VERSION", self.content)
        self.assertIn("$MSYSTEM", self.content)

    def test_cross_platform_skip_behavior(self):
        self.assertIn("Skipped", self.content)
        self.assertIn("No linters available", self.content)

    def test_cross_platform_installation_guidance(self):
        self.assertIn("Installation guidance", self.content)
        self.assertIn("rustup component add clippy", self.content)

    def test_incremental_review_tracking(self):
        self.assertIn("Incremental Review Tracking", self.content)

    def test_ccr_state_json(self):
        self.assertIn("ccr-state.json", self.content)

    def test_ccr_state_fields(self):
        for field in ["base_hash", "head_hash", "reviewed_files",
                       "findings_by_file", "last_decision"]:
            with self.subTest(field=field):
                self.assertIn(field, self.content)

    def test_incremental_precedence_rules(self):
        self.assertIn("--force-full", self.content)
        self.assertIn("Precedence rules", self.content)
        self.assertIn("re-review all files that differ", self.content)

    def test_incremental_procedure(self):
        self.assertIn("Incremental procedure", self.content)
        self.assertIn("git diff <old_head>..HEAD --name-only", self.content)

    def test_format_flag(self):
        self.assertIn("--format", self.content)
        self.assertIn("markdown|json|both", self.content)

    def test_chunk_flag(self):
        self.assertIn("--chunk", self.content)
        self.assertIn("--chunk <module>", self.content)

    def test_force_full_flag(self):
        self.assertIn("--force-full", self.content)
        self.assertIn("bypass", self.content)
        self.assertIn("incremental review tracking", self.content)

    def test_fix_review_cycle(self):
        self.assertIn("## Phase 3.5", self.content)
        self.assertIn("Fix-Review Cycle", self.content)
        self.assertIn("REVIEW_MAX_ITERATIONS", self.content)

    def test_termination_signals(self):
        self.assertIn("Termination Signals", self.content)
        self.assertIn('decision == "APPROVE"', self.content)
        self.assertIn("No new findings", self.content)
        self.assertIn("Max iterations reached", self.content)

    def test_json_format_both_separator(self):
        self.assertIn("---REVIEW_JSON---", self.content)


class TestEdgeCases(_BaseReviewComplianceTest):
    """Edge cases and fallbacks: no gh, no git, no changes, large PR, etc."""

    def test_no_gh_fallback(self):
        self.assertIn("No `gh` CLI", self.content)
        self.assertIn("Skip GitHub posting", self.content)

    def test_no_git_repo_error(self):
        self.assertIn("Not a git repository", self.content)

    def test_no_changes_message(self):
        self.assertIn("Nothing to review", self.content)

    def test_pr_not_found_error(self):
        self.assertIn("PR not found", self.content)

    def test_validation_required_hard_failure(self):
        self.assertIn("Validation commands not found (required)", self.content)
        self.assertIn("non-zero", self.content)

    def test_validation_optional_skip(self):
        self.assertIn("Validation commands not found (optional)", self.content)

    def test_large_pr_edge_case(self):
        self.assertIn("Large PR (>50 files)", self.content)

    def test_incremental_bypass(self):
        self.assertIn("Incremental review bypass", self.content)
        self.assertIn("corrupt or unreadable", self.content)

    def test_max_iterations_env(self):
        self.assertIn("REVIEW_MAX_ITERATIONS", self.content)


class TestCleanup(_BaseReviewComplianceTest):
    """Cleanup section: temp files, ccr-state.json preservation."""

    def test_cleanup_section_exists(self):
        self.assertIn("## Cleanup", self.content)

    def test_temp_file_deletion(self):
        self.assertIn("temporary files", self.content)

    def test_ccr_state_preservation(self):
        self.assertIn("Preserve `ccr-state.json`", self.content)

    def test_full_reset_only_on_explicit_request(self):
        self.assertIn("explicitly requests a full reset", self.content)


class TestContentQuality(_BaseReviewComplianceTest):
    """Content quality: mode selection table, gh fallback, reporting."""

    def test_mode_selection_table(self):
        self.assertIn("$REVIEW_MODE", self.content)
        self.assertIn("$REVIEW_TARGET", self.content)
        self.assertIn("Local", self.content)
        self.assertIn("Commit", self.content)
        self.assertIn("Branch compare", self.content)
        self.assertIn("PR mode", self.content)

    def test_gh_pr_commands(self):
        self.assertIn("gh pr view", self.content)
        self.assertIn("gh pr diff", self.content)
        self.assertIn("gh pr review", self.content)

    def test_gh_auth_check(self):
        self.assertIn("gh auth status", self.content)

    def test_project_context_detection(self):
        self.assertIn("package.json", self.content)
        self.assertIn("Cargo.toml", self.content)
        self.assertIn("go.mod", self.content)
        self.assertIn("pyproject.toml", self.content)

    def test_conventions_files(self):
        self.assertIn("AGENTS.md", self.content)
        self.assertIn("CLAUDE.md", self.content)
        self.assertIn("CONTRIBUTING.md", self.content)
        self.assertIn(".editorconfig", self.content)

    def test_markdown_report_structure(self):
        self.assertIn("Code Review Report", self.content)
        self.assertIn("## Summary", self.content)
        self.assertIn("## Findings by Severity", self.content)
        self.assertIn("## Validation Results", self.content)
        self.assertIn("## Files Reviewed", self.content)

    def test_scope_flags(self):
        self.assertIn("-t all", self.content)
        self.assertIn("-t staged", self.content)
        self.assertIn("-t committed", self.content)
        self.assertIn("-t uncommitted", self.content)
        self.assertIn("--base <branch>", self.content)
        self.assertIn("--base-commit <sha>", self.content)
        self.assertIn("--dir <path>", self.content)
        self.assertIn("--json", self.content)

    def test_review_scope_storage(self):
        self.assertIn("$REVIEW_SCOPE", self.content)


if __name__ == "__main__":
    unittest.main()
