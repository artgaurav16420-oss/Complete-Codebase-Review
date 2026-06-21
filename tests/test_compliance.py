"""Compliance tests for SKILL.md.

Checks structural, content, cross-platform, fix-plan, and integration
requirements against the SKILL.md file. Uses unittest as the canonical
test framework (see ADR-003).

Usage:
    python tests/test_compliance.py
"""
import os
import re
import unittest
from pathlib import Path


# Reference list of all 14 specialist agents. Used to count how many distinct
# agent names appear in SKILL.md (exact string match). Not all 14 names may
# match if SKILL.md uses slightly different titles. The 2-mismatch allowance
# applies only to test_at_least_12_agents; other tests may enforce stricter
# requirements for all 14 agents.
_ALL_AGENTS = [
    "Architecture Analyzer", "Code Quality Auditor",
    "Security Posture", "Tech Debt Tracker",
    "Test Health Auditor", "Dependency Auditor",
    "Documentation Auditor", "Build & CI Auditor",
    "Performance Baseline", "Database & Schema",
    "UI/UX Auditor", "DevOps & Infra",
    "Standards Compliance", "Process Quality (Karpathy Compliance)",
]


def _has_changelog():
    path = os.path.join(os.path.dirname(__file__), "..", "CHANGELOG.md")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return 'Changelog' in f.read() or 'Change Log' in f.read()
    return False


# --- unittest.TestCase wrappers (canonical test framework) ---


class _BaseComplianceTest(unittest.TestCase):
    """Base class: loads SKILL.md content once per class."""

    @classmethod
    def setUpClass(cls):
        cls.skill_path = os.path.join(os.path.dirname(__file__), "..", "SKILL.md")
        with open(cls.skill_path, "r", encoding="utf-8") as f:
            cls.content = f.read()


class TestStructural(_BaseComplianceTest):
    """Structural checks: YAML frontmatter, command fields, required sections."""

    def test_skill_md_exists_on_disk(self):
        self.assertTrue(os.path.exists(self.skill_path))

    def test_karpathy_md_exists_on_disk(self):
        self.assertTrue(os.path.exists(
            os.path.join(os.path.dirname(self.skill_path), "karpathy-guidelines.md")))

    def test_yaml_frontmatter(self):
        self.assertIsNotNone(re.search(r'(?s)^---\r?\n.+\r?\n---', self.content))
        self.assertIsNotNone(re.search(r'(?m)^name: ', self.content))
        self.assertIn('description: Use when', self.content)
        self.assertIsNotNone(re.search(r'(?m)^version: ', self.content))

    def test_version_sources_stay_in_sync(self):
        repo_root = Path(self.skill_path).resolve().parent
        skill_version = re.search(r'(?m)^version:\s*([^\s]+)', self.content).group(1)
        pyproject = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
        pyproject_version = re.search(
            r'(?m)^version\s*=\s*"([^"]+)"', pyproject
        ).group(1)
        install_py = (repo_root / "install.py").read_text(encoding="utf-8")

        self.assertEqual(skill_version, pyproject_version)
        self.assertIn("get_version()", install_py)

        changelog = (repo_root / "CHANGELOG.md").read_text(encoding="utf-8")
        changelog_version = re.search(
            r'(?m)^## v([^\s(]+)', changelog
        ).group(1)
        self.assertEqual(changelog_version, pyproject_version)

    def test_no_workflow_summary_in_description(self):
        desc_match = re.search(r'description: (.*?)(?:\n|$)', self.content)
        self.assertIsNotNone(desc_match)
        self.assertFalse(
            re.search(r'(spawn|synthes|phase|agent|parallel)', desc_match.group(1)))

    def test_command_frontmatter_fields(self):
        self.assertIn('user-invocable: true', self.content)
        self.assertIn('argument-hint:', self.content)
        self.assertIn('allowed-tools:', self.content)
        self.assertIn('Task', self.content)
        self.assertIn('effort: ${CODE_REVIEW_EFFORT:-max}', self.content)
        self.assertIsNone(re.search(r'(?m)^model: opus', self.content))
        self.assertIn('$ARGUMENTS', self.content)
        self.assertIn('$TARGET_DIR', self.content)

    def test_required_sections_present(self):
        sections = [
            "## Overview", "## When to Use", "## Phase 1", "## Phase 2",
            "## Phase 3", "Non-Negotiable Rules", "Anti-Rationalization",
            "Red Flags", "Output Format", "Graceful Degradation",
            "Common Mistakes", "Cross-Boundary", "Specialist Agents",
            "Web Verification", "Cross-platform", "Cleanup",
        ]
        for section in sections:
            with self.subTest(section=section):
                self.assertIn(section, self.content)


class TestContentQuality(_BaseComplianceTest):
    """Content quality: DA mentions, agents, health scores, non-negotiable rules."""

    def test_devils_advocate_mentioned(self):
        self.assertIsNotNone(
            re.search(r"devil'?s advocate", self.content, re.IGNORECASE))

    def test_da_verdicts_defined(self):
        for v in ["CONFIRMED", "PLAUSIBLE", "QUESTIONABLE", "REJECTED"]:
            with self.subTest(verdict=v):
                self.assertIn(v, self.content)

    def test_specialist_agent_table(self):
        self.assertIn('Architecture Analyzer', self.content)
        self.assertIn('Security Posture', self.content)

    def test_at_least_12_agents(self):
        matched = sum(1 for a in _ALL_AGENTS if a in self.content)
        self.assertGreaterEqual(matched, 12)

    def test_skill_loading_per_agent(self):
        self.assertIn('Load a relevant skill', self.content)
        self.assertIn('Skill tool', self.content)

    def test_discovery_and_roadmap_phases(self):
        self.assertIn('Discovery', self.content)
        self.assertIsNotNone(
            re.search(r'Roadmap', self.content, re.IGNORECASE))

    def test_tech_debt_and_health_scores(self):
        self.assertIsNotNone(
            re.search(r'tech debt', self.content, re.IGNORECASE))
        self.assertIsNotNone(
            re.search(r'health', self.content, re.IGNORECASE))

    def test_phased_roadmap(self):
        self.assertIn('Phase 1', self.content)
        self.assertIn('Phase 2', self.content)

    def test_passive_monitoring_pattern(self):
        self.assertIn('do nothing else', self.content)

    def test_blocks_partial_results(self):
        self.assertIsNotNone(
            re.search(r'ALL N', self.content, re.IGNORECASE))

    def test_graceful_degradation(self):
        self.assertIsNotNone(
            re.search(r'Agent fail', self.content, re.IGNORECASE))

    def test_web_verification_and_cleanup(self):
        self.assertIn('## Web Verification', self.content)
        self.assertIn('Cleanup', self.content)

    def test_output_destination_ask(self):
        self.assertTrue(
            'Ask user' in self.content or
            'AskUserQuestion' in self.content or
            'Where should I write' in self.content)

    def test_unverified_tag(self):
        self.assertIn('UNVERIFIED', self.content)

    def test_sample_output_and_changelog(self):
        self.assertTrue(
            'Sample Output' in self.content or
            'Example Report' in self.content)
        self.assertTrue(
            ('Changelog' in self.content or 'Change Log' in self.content) or _has_changelog())

    def test_non_negotiable_rules_table(self):
        rule_lines = [
            l for l in self.content.split('\n')
            if re.match(r'^\|\s*\d+\s*\|', l)
        ]
        self.assertGreaterEqual(len(rule_lines), 10)

    def test_dynamic_timeout_threshold(self):
        self.assertIn('${CODE_REVIEW_TIMEOUT_SEC:-900}', self.content)
        self.assertIn('75%', self.content)

    def test_web_verify_mandatory(self):
        self.assertIn('Web verification MANDATORY', self.content)

    def test_never_modify_codebase_rule(self):
        self.assertIn('NEVER modify the codebase', self.content)

    def test_fix_plan_waits_for_approval(self):
        self.assertIn('MUST wait for user approval', self.content)

    def test_anti_rationalization_table(self):
        anti_rat_lines = [
            l for l in self.content.split('\n')
            if re.match(r'^\| "[^"]*" \| .+', l)
        ]
        self.assertGreaterEqual(len(anti_rat_lines), 6)
        self.assertIn('Web verification takes too long', self.content)

    def test_red_flags_list(self):
        red_flag_lines = [
            l for l in self.content.split('\n')
            if re.match(r'^- ', l)
            and not any(x in l for x in ['User', 'source', 'title', 'rubric'])
        ]
        self.assertGreaterEqual(len(red_flag_lines), 5)
        for phrase in ['75%', 'insufficient coverage',
                        'Skipping web verification',
                        'Modifying any codebase file']:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.content)


class TestCrossPlatform(_BaseComplianceTest):
    """Cross-platform command coverage."""

    def test_os_detection(self):
        self.assertTrue(
            '$IsWindows' in self.content or 'uname' in self.content)

    def test_windows_unix_commands(self):
        self.assertIn('Get-ChildItem', self.content)
        self.assertIn('find', self.content)

    def test_temp_dir_fallback(self):
        self.assertTrue(
            any(x in self.content for x in [
                '$env:TEMP', '$TMPDIR', '/tmp',
                'Fall back to OS temporary directory',
            ]))

    def test_git_aware_discovery(self):
        self.assertIn('git', self.content)
        self.assertTrue(
            'churn' in self.content or 'history' in self.content)

    def test_cross_agent_conflict_resolution(self):
        self.assertTrue(
            'cross-agent' in self.content or 'conflict' in self.content)

    def test_da_verdict_in_output(self):
        self.assertTrue(
            'DA Verdict' in self.content or 'CONFIRMED' in self.content)

    def test_readonly_declaration(self):
        self.assertTrue(
            'NEVER modifies the codebase' in self.content or
            re.search(r'read.only', self.content, re.IGNORECASE) is not None)


class TestFixPlan(_BaseComplianceTest):
    """Phase 4 fix plan: task IDs, approval, priority, re-review."""

    def test_phase_4_section_exists(self):
        self.assertIn('## Phase 4', self.content)

    def test_fix_plan_table(self):
        self.assertIn('Task ID', self.content)
        self.assertIn('T-001', self.content)

    def test_user_approval_gate(self):
        self.assertIn('Do NOT apply', self.content)
        self.assertIn('user explicitly', self.content)

    def test_selective_approval(self):
        self.assertIn('Task IDs', self.content)
        self.assertIn('"all"', self.content)

    def test_post_fix_verification(self):
        self.assertTrue(
            'Post-Fix Verification' in self.content or 'Verify Fixes' in self.content)

    def test_critical_before_high(self):
        self.assertIn('CRITICAL items first', self.content)

    def test_baseline_snapshot(self):
        self.assertIn('baseline', self.content)
        self.assertIn('trend', self.content)

    def test_re_review_guidance(self):
        self.assertTrue(
            'Re-review' in self.content or 'follow-up' in self.content)

    def test_estimate_conflicts_logged(self):
        self.assertIn('EST-CONFLICT', self.content)

    def test_phase_5_section_exists(self):
        self.assertIn('## Phase 5', self.content)

    def test_independent_review_phase(self):
        self.assertTrue(
            'Independent Review' in self.content or 'independent agent' in self.content)

    def test_full_test_suite_run(self):
        self.assertTrue(
            'full test suite' in self.content or 'test suite' in self.content)

    def test_pr_creation_phase(self):
        """Phase 5d creates a pull request with applied fixes."""
        self.assertIn('Create Pull Request', self.content)

    def test_review_on_pr_phase(self):
        """Phase 5f enters external review loop with AI bot comments."""
        self.assertIn('External Review Loop', self.content)

    def test_autofix_loop_phase(self):
        """Phase 5c implements the local review loop with auto-correction."""
        self.assertIn('Local Review Loop', self.content)
        self.assertIn('REVIEW_MAX_ITERATIONS', self.content)

    def test_pr_requires_gh(self):
        """Phase 5e checks gh CLI availability before creating PR."""
        self.assertIn('gh auth status', self.content)

    def test_skills_loaded_from_skill_dir(self):
        """Phase 5 agents load skills from SKILL_DIR, not system path."""
        self.assertIn('$SKILL_DIR/karpathy-guidelines.md', self.content)

    def test_autofix_auto_applies(self):
        """Phase 5c auto-applies corrections in the local review loop."""
        self.assertIn('no user approval needed', self.content)
        self.assertIn('automatically', self.content)


class TestIntegration(_BaseComplianceTest):
    """Integration checks across all pipeline phases."""

    def test_baseline_failure_coverage(self):
        for phrase in ['Discovery', 'Specialist Agents']:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.content)
        self.assertTrue(
            re.search(r'fewer than \d+% of agents complete', self.content)
            is not None or 'parallel' in self.content)
        self.assertIn('Per-Domain', self.content)
        self.assertIn('severity', self.content)

    def test_discovery_phase_collects_metadata(self):
        self.assertIn('Languages', self.content)
        self.assertIn('Frameworks', self.content)
        self.assertIn('git', self.content)
        self.assertTrue(
            re.search(r'churn|history', self.content, re.IGNORECASE)
            is not None)
        self.assertTrue(
            re.search(r'Write.*manifest', self.content) is not None or
            'ccr-manifest' in self.content)
        self.assertIn('Architecture & Design', self.content)
        self.assertIn('Security Posture', self.content)
        self.assertIn('Applies When', self.content)
        self.assertIn('Environment Check', self.content)
        self.assertIn('Critical?', self.content)

    def test_parallel_analysis_all_14_agents(self):
        matched = sum(1 for a in _ALL_AGENTS if a in self.content)
        self.assertGreaterEqual(matched, 14)
        self.assertIn('Methodology', self.content)
        self.assertIn('Quantify findings', self.content)
        self.assertIn('Web Verify', self.content)
        self.assertIn('subagent_type:', self.content)
        self.assertIn('SKILL_DIR', self.content)

    def test_synthesis_dedup_and_normalize(self):
        self.assertIn('Deduplicate', self.content)
        self.assertIn('Normalize severity', self.content)
        self.assertTrue(
            'cross-agent' in self.content or 'conflict' in self.content)
        self.assertIn('Quantify tech debt', self.content)

    def test_synthesis_da_workflow(self):
        self.assertIn('Challenge EVERY', self.content)
        self.assertIn('Web-verify each claim', self.content)
        self.assertIn('Independently read code', self.content)
        for v in ["CONFIRMED", "PLAUSIBLE", "QUESTIONABLE", "REJECTED"]:
            with self.subTest(verdict=v):
                self.assertIn(v, self.content)

    def test_roadmap_has_three_phases(self):
        self.assertIn('Phase 1', self.content)
        self.assertIn('Phase 2', self.content)
        self.assertIn('Phase 3', self.content)
        self.assertIn('impact vs effort', self.content)

    def test_output_and_cleanup(self):
        self.assertIn('Print the full health report to stdout', self.content)
        self.assertIn('Delete', self.content)
        self.assertIn('temp', self.content)
        self.assertIn('Executive Summary', self.content)
        self.assertIn('Per-Domain Scores', self.content)
        self.assertIn('DA Verdict', self.content)
        self.assertIn('CODE_REVIEW_FILTER', self.content)
        self.assertIn('critical-high', self.content)

    def test_fix_plan_tasks(self):
        self.assertIn('Task ID', self.content)
        self.assertIn('T-001', self.content)
        self.assertIn('Do NOT apply', self.content)
        self.assertIn('user explicitly', self.content)
        self.assertIn('Task IDs', self.content)
        self.assertIn('"all"', self.content)
        self.assertIn('skip', self.content)
        self.assertIn('CRITICAL items first', self.content)
        self.assertIn('baseline', self.content)
        self.assertIn('trend', self.content)
        self.assertIn('EST-CONFLICT', self.content)

    def test_safety_readonly(self):
        self.assertIn('NEVER modify the codebase', self.content)
        self.assertIn('NEVER modify the codebase during Phases 1-3', self.content)
        self.assertIn('MUST wait for user approval', self.content)
        self.assertIn('Modifying any codebase file', self.content)
        self.assertIn('without explicit user approval', self.content)


if __name__ == "__main__":
    unittest.main()
