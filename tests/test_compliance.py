"""Compliance tests for SKILL.md.

Checks structural, content, cross-platform, fix-plan, and integration
requirements against the SKILL.md file. Uses a custom ``check()`` /
``make_checker()`` DSL for compact assertion of 130+ string-matching tests
without requiring pytest or any third-party dependency.

Usage:
    python tests/test_compliance.py

Returns exit code 0 on all-pass, 1 on any failure.
"""
import os
import re
import sys
import unittest


def check(test_name, condition):
    if condition:
        print(f"\033[92mPASS:\033[0m {test_name}")
        return True
    else:
        print(f"\033[91mFAIL:\033[0m {test_name}")
        return False


def make_checker(section_name):
    """Create a paired (run_check, result) closure for a test section.

    Args:
        section_name: Display name for the section (printed as header).

    Returns:
        Tuple of (run_check, result). run_check accumulates pass/fail;
        result() returns (pass_count, fail_count).
    """
    print(f"\033[96m=== {section_name} ===\033[0m")
    pass_count = 0
    fail_count = 0
    def run_check(test_name, condition):
        nonlocal pass_count, fail_count
        if check(test_name, condition):
            pass_count += 1
        else:
            fail_count += 1
    def result():
        return pass_count, fail_count
    return run_check, result


def test_structural(content, skill_path):
    """Check SKILL.md existence, YAML frontmatter, and version field."""
    run_check, result = make_checker("Structural")
    run_check("SKILL.md exists", os.path.exists(skill_path))
    karpathy_path = os.path.join(os.path.dirname(skill_path), "karpathy-guidelines.md")
    run_check(
        "karpathy-guidelines.md exists alongside SKILL.md",
        os.path.exists(karpathy_path)
    )
    run_check("Has YAML frontmatter", re.search(r'(?s)^---\r?\n.+\r?\n---', content) is not None)
    run_check("Has name", re.search(r'(?m)^name: ', content) is not None)
    run_check("Description starts with Use when", 'description: Use when' in content)
    run_check("Has version field", re.search(r'(?m)^version: ', content) is not None)

    desc_match = re.search(r'description: (.*?)(?:\n|$)', content)
    has_summary = bool(
        desc_match
        and re.search(
            r'(spawn|synthes|phase|agent|parallel)', desc_match.group(1)
        )
    )
    run_check("No workflow summary in description", not has_summary)
    return result()

def test_command_frontmatter(content):
    """Check user-invocable, argument-hint, effort, and model fields."""
    run_check, result = make_checker("Command Frontmatter")
    run_check("Has user-invocable: true", 'user-invocable: true' in content)
    run_check("Has argument-hint", 'argument-hint:' in content)
    run_check("Has allowed-tools", 'allowed-tools:' in content)
    run_check("Has allowed-tools including Task", 'allowed-tools:' in content and 'Task' in content)
    run_check("Has effort: max", 'effort: ${CODE_REVIEW_EFFORT:-max}' in content)
    run_check("Model: opus is absent", re.search(r'(?m)^model: opus', content) is None)
    run_check("References $ARGUMENTS", '$ARGUMENTS' in content)
    run_check("Sets $TARGET_DIR from args", '$TARGET_DIR' in content)
    return result()

def test_required_sections(content):
    """Verify all required section headings exist in SKILL.md."""
    run_check, result = make_checker("Required Sections")
    sections = [
        "## Overview", "## When to Use", "## Phase 1", "## Phase 2", "## Phase 3",
        "Non-Negotiable Rules", "Anti-Rationalization", "Red Flags",
        "Output Format", "Graceful Degradation", "Common Mistakes",
        "Cross-Boundary", "Specialist Agents", "Web Verification",
        "Cross-platform", "Cleanup"
    ]
    for section in sections:
        run_check(f"Has section: {section}", section in content)
    return result()

def test_content_quality(content):
    """Check DA mentions, specialist agent table, health scores, roadmaps."""
    run_check, result = make_checker("Content Quality")
    run_check("Mentions devil's advocate", re.search(r"devil'?s advocate", content, re.IGNORECASE) is not None)
    run_check("Mentions CONFIRMED", 'CONFIRMED' in content)
    run_check("Has specialist agent table", 'Architecture Analyzer' in content and 'Security Posture' in content)

    agents = [
        "Architecture Analyzer",
        "Code Quality Auditor",
        "Security Posture",
        "Tech Debt Tracker",
        "Test Health Auditor",
        "Dependency Auditor",
        "Documentation Auditor",
        "Build & CI Auditor",
        "Performance Baseline",
        "Database & Schema",
        "UI/UX Auditor",
        "DevOps & Infra",
        "Standards Compliance",
        "Process Quality (Karpathy Compliance)",
    ]
    matched_agents = sum(1 for agent in agents if agent in content)
    run_check("Has at least 12 specialist agents", matched_agents >= 12)
    run_check("Has UI/UX Auditor agent", 'UI/UX Auditor' in content)
    run_check("Requires skill loading per agent", 'Load a relevant skill' in content and 'Skill tool' in content)
    run_check("Has Discovery phase", 'Discovery' in content)
    run_check("Has Roadmap phase", re.search(r'Roadmap', content, re.IGNORECASE) is not None)
    run_check("Has tech debt quantification", re.search(r'tech debt', content, re.IGNORECASE) is not None)
    run_check("Has health score", re.search(r'health', content, re.IGNORECASE) is not None)
    run_check("Has phased roadmap", 'Phase 1' in content and 'Phase 2' in content)
    run_check("Blocks passive monitoring", 'do nothing else' in content or 'No messages, no drafting, no polling' in content)
    run_check("Blocks partial results", re.search(r'ALL N', content, re.IGNORECASE) is not None)
    run_check("Has graceful degradation for agent failure", re.search(r'Agent fail', content, re.IGNORECASE) is not None or 'crash' in content)
    run_check("Has web verification section", '## Web Verification' in content)
    run_check("Has cleanup phase", 'Cleanup' in content)
    run_check("Has output destination ask", 'Ask user' in content or 'AskUserQuestion' in content or 'Where should I write' in content)
    run_check("Mentions UNVERIFIED", 'UNVERIFIED' in content)
    run_check("Has sample output section", 'Sample Output' in content or 'Example Report' in content)
    run_check("Has changelog section", 'Changelog' in content or 'Change Log' in content)
    return result()

def test_cross_platform(content):
    """Check Windows/Unix directory commands, temp dir, OS detection."""
    run_check, result = make_checker("Cross-Platform")
    run_check("Has cross-platform directory commands", 'Get-ChildItem' in content and 'find' in content)
    run_check("Has OS detection", '$IsWindows' in content or 'uname' in content)
    run_check("Has cross-platform temp directory", '$env:TEMP' in content or '$TMPDIR' in content)
    run_check("Has git-aware discovery", 'git' in content and ('churn' in content or 'history' in content))
    run_check("Has cross-agent conflict resolution", 'cross-agent' in content or 'conflict' in content)
    run_check("Has DA verdict in output format", 'DA Verdict' in content or 'CONFIRMED' in content)
    run_check("Declares READ-ONLY", 'NEVER modifies the codebase' in content or re.search(r'read.only', content, re.IGNORECASE) is not None)
    return result()

def test_fix_plan(content):
    """Check Phase 4 fix-plan table, approval flow, and post-fix verification."""
    run_check, result = make_checker("Fix Plan")
    run_check("Has Phase 4 section", '## Phase 4' in content)
    run_check("Has fix plan table", 'Task ID' in content and 'T-001' in content)
    run_check("Asks user for approval", 'Do NOT apply' in content and 'user explicitly' in content)
    run_check("Only applies on approved Task IDs", 'Task IDs' in content or '"all"' in content)
    run_check("Has post-fix verification phase", 'Phase 4g' in content or 'Verify Fixes' in content)
    run_check("Applies CRITICAL before HIGH", 'CRITICAL items first' in content)
    run_check("Has baseline snapshot for trend", 'baseline' in content and 'trend' in content)
    run_check("Has re-review guidance", 'Re-review' in content or 'follow-up' in content)
    return result()

def test_baseline_failure_coverage(content):
    """Check that failure-mode coverage includes shallow-scan, single-pass, and no-structure."""
    run_check, result = make_checker("Baseline Failure Coverage")
    run_check("Covers shallow scan failure", 'Discovery' in content and 'Specialist Agents' in content)
    run_check("Covers single-pass bias failure", re.search(r'fewer than \d+% of agents complete', content) is not None or ('fewer than' in content and 'parallel' in content))
    run_check("Covers no-structure failure", 'Per-Domain' in content and 'severity' in content)
    run_check("Covers inconsistent depth failure", 'Prioritize core' in content and 'not analyzed' in content)
    run_check("Covers no-quantification failure", 'quantified metric' in content or 'quantified' in content)
    run_check("Covers no-roadmap failure", 'Phase 1' in content and 'Phase 2' in content and 'Phase 3' in content)
    return result()

def test_non_negotiable_rules(content):
    """Check rule count, dynamic timeout, web verification, and read-only rules."""
    run_check, result = make_checker("Non-Negotiable Rules")
    rule_lines = [line for line in content.split('\n') if re.match(r'^\|\s*\d+\s*\|', line)]
    run_check("Has at least 10 rules", len(rule_lines) >= 10)
    run_check("Rule 1: Dynamic timeout per agent + 75% threshold", re.search(r'\$\{CODE_REVIEW_TIMEOUT_SEC:-900\}', content) is not None and '75%' in content)
    run_check("Rule 8: Web verification mandatory", 'Web verification MANDATORY' in content)
    run_check("Rule 9: NEVER modify codebase", 'NEVER modify the codebase' in content)
    run_check("Rule 10: Fix plan waits for approval", 'MUST wait for user approval' in content)
    return result()

def test_anti_rationalization(content):
    """Check anti-rationalization table entries and web verification mention."""
    run_check, result = make_checker("Anti-Rationalization")
    anti_rat_lines = [line for line in content.split('\n') if re.match(r'^\| ".+ | ".+', line)]
    run_check("Has at least 6 entries", len(anti_rat_lines) >= 6)
    run_check("Has web verification rationalization", 'Web verification takes too long' in content)
    return result()

def test_red_flags(content):
    """Check red-flag count and coverage of agent failure, skipped web-verify, file-modification."""
    run_check, result = make_checker("Red Flags")
    red_flag_lines = [line for line in content.split('\n') if re.match(r'^- ', line) and not any(x in line for x in ['User', 'source', 'title', 'rubric'])]
    run_check("Has at least 5 red flags", len(red_flag_lines) >= 5)
    run_check("Stops on insufficient agent coverage", '75%' in content or 'insufficient coverage' in content)
    run_check("Stops on skipped web verification", 'Skipping web verification' in content)
    run_check("Stops on modifying files", 'Modifying any codebase file' in content)
    return result()

def test_integration_discovery_phase(content):
    """Check Phase 1 discovery collects languages, git history, manifest, and health dimensions."""
    run_check, result = make_checker("Integration: Discovery Phase")
    run_check("Discovery collects languages", 'Languages' in content and 'Frameworks' in content)
    run_check("Discovery collects git history", 'git' in content and re.search(r'churn|history', content, re.IGNORECASE) is not None)
    run_check("Discovery writes manifest", re.search(r'Write.*manifest', content) is not None or 'ccr-manifest' in content)
    run_check("Discovery has health dimension table", 'Architecture & Design' in content and 'Security Posture' in content)
    run_check("Discovery selects dimensions by criteria", 'Applies When' in content)
    run_check("Discovery has environment check step", 'Environment Check' in content and 'Critical?' in content)
    return result()

def test_integration_parallel_analysis(content):
    """Check Phase 2 spawns all 14 agents with methodology, quantification, web-verify, skill-loading."""
    run_check, result = make_checker("Integration: Parallel Analysis")
    agent_names = [
        "Architecture Analyzer",
        "Code Quality Auditor",
        "Security Posture",
        "Tech Debt Tracker",
        "Test Health Auditor",
        "Dependency Auditor",
        "Documentation Auditor",
        "Build & CI Auditor",
        "Performance Baseline",
        "Database & Schema",
        "UI/UX Auditor",
        "DevOps & Infra",
        "Standards Compliance",
        "Process Quality (Karpathy Compliance)",
    ]
    matched_agent_names = sum(1 for agent in agent_names if agent in content)
    run_check("All 14 agents have unique coverage", matched_agent_names >= 14)
    run_check("Each agent has methodology requirement", 'Methodology' in content and 'Step-by-step' in content)
    run_check("Each agent must quantify findings", 'Quantify findings' in content or 'Quantification' in content)
    run_check("Each agent must web verify", 'Web Verify' in content)
    run_check("Each agent loads a skill", 'Load a relevant skill' in content and 'Skill tool' in content)
    run_check("Parallel orchestration is passive", 'do nothing else' in content and 'No messages, no drafting, no polling' in content)
    run_check("Task invocation example provided", 'task name:' in content or 'subagent_type:' in content)
    run_check("SKILL_DIR injected into agent prompts", 'SKILL_DIR' in content)
    return result()

def test_integration_synthesis_roadmap(content):
    """Check Phase 3 dedup, severity normalization, DA verdicts, and 3-phase roadmap."""
    run_check, result = make_checker("Integration: Synthesis + Roadmap")
    run_check("Synthesis deduplicates findings", 'Deduplicate' in content)
    run_check("Synthesis normalizes severity", 'Normalize severity' in content)
    run_check("Synthesis resolves cross-agent conflicts", 'cross-agent' in content or 'conflict' in content)
    run_check("Synthesis quantifies tech debt", 'Quantify tech debt' in content)
    run_check("Roadmap has 3 phases", 'Phase 1' in content and 'Phase 2' in content and 'Phase 3' in content)
    run_check("Roadmap prioritizes by impact vs effort", 'impact vs effort' in content)
    run_check("DA challenges every finding", 'Challenge EVERY' in content)
    run_check("DA web-verifies claims", 'Web-verify each claim' in content)
    run_check("DA independently reads code", 'Independently read code' in content)
    run_check("DA uses CONFIRMED/PLAUSIBLE/QUESTIONABLE/REJECTED", all(x in content for x in ['CONFIRMED', 'PLAUSIBLE', 'QUESTIONABLE', 'REJECTED']))
    return result()

def test_integration_output_cleanup(content):
    """Check output destination, temp cleanup, executive summary, per-domain scores, filter."""
    run_check, result = make_checker("Integration: Output + Cleanup")
    run_check("Asks user for output destination", 'Where should I write' in content)
    run_check("Deletes temp files after output", 'Delete' in content and 'temp' in content)
    run_check("Health report has executive summary", 'Executive Summary' in content)
    run_check("Health report has per-domain scores", 'Per-Domain Scores' in content)
    run_check("Health report has DA verdict column", 'DA Verdict' in content)
    run_check("Has CODE_REVIEW_FILTER env var", 'CODE_REVIEW_FILTER' in content)
    run_check("Filters by critical-high", 'critical-high' in content)
    return result()

def test_integration_fix_plan(content):
    """Check task IDs, approval gates, selective apply, 'all'/'skip' shortcuts, estimate conflicts."""
    run_check, result = make_checker("Integration: Fix Plan")
    run_check("Fix plan generates tasks with IDs", 'Task ID' in content and 'T-001' in content)
    run_check("Fix plan requires user approval", 'Do NOT apply' in content and 'user explicitly' in content)
    run_check("Fix plan supports selective approval", 'Task IDs' in content)
    run_check("Fix plan supports 'all' shortcut", '"all"' in content)
    run_check("Fix plan supports 'skip' to exit", 'skip' in content)
    run_check("Applies CRITICAL before HIGH", 'CRITICAL items first' in content)
    run_check("Has baseline snapshot for trend", 'baseline' in content and 'trend' in content)
    run_check("Has re-review guidance", 'Re-review' in content or 'follow-up' in content)
    run_check("EST-CONFLICT logged on estimate variance", 'EST-CONFLICT' in content)
    return result()

def test_integration_safety(content):
    """Check read-only declaration, no-auto-apply rule, modifying-files red flag."""
    run_check, result = make_checker("Integration: Safety")
    run_check("Declares READ-ONLY", 'NEVER modify the codebase' in content or 'READ-ONLY' in content)
    run_check("Rule 9: no codebase modification", 'NEVER modify the codebase during Phases 1-3' in content)
    run_check("Rule 10: no auto-apply", 'MUST wait for user approval' in content)
    run_check("Red flag for modifying files", 'Modifying any codebase file' in content)
    run_check("Red flag for auto-apply", 'without explicit user approval' in content)
    return result()

def test_integration_cross_platform(content):
    """Check OS detection, Windows Get-ChildItem, Unix find, temp-dir fallback."""
    run_check, result = make_checker("Integration: Cross-Platform")
    run_check("Detects OS", '$IsWindows' in content or 'uname' in content)
    run_check("Windows commands available", 'Get-ChildItem' in content)
    run_check("Unix commands available", 'find' in content)
    run_check("Temp dir fallback", any(x in content for x in ['$env:TEMP', '$TMPDIR', '/tmp', 'Fall back to OS temporary directory']))
    return result()

# --- unittest.TestCase wrappers (dual-mode with main()) ---


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
        agents = [
            "Architecture Analyzer", "Code Quality Auditor",
            "Security Posture", "Tech Debt Tracker",
            "Test Health Auditor", "Dependency Auditor",
            "Documentation Auditor", "Build & CI Auditor",
            "Performance Baseline", "Database & Schema",
            "UI/UX Auditor", "DevOps & Infra",
            "Standards Compliance", "Process Quality (Karpathy Compliance)",
        ]
        matched = sum(1 for a in agents if a in self.content)
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
            'Changelog' in self.content or 'Change Log' in self.content)

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
            if re.match(r'^\| ".+ | ".+', l)
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
            'Phase 4g' in self.content or 'Verify Fixes' in self.content)

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
        agents = [
            "Architecture Analyzer", "Code Quality Auditor",
            "Security Posture", "Tech Debt Tracker",
            "Test Health Auditor", "Dependency Auditor",
            "Documentation Auditor", "Build & CI Auditor",
            "Performance Baseline", "Database & Schema",
            "UI/UX Auditor", "DevOps & Infra",
            "Standards Compliance", "Process Quality (Karpathy Compliance)",
        ]
        matched = sum(1 for a in agents if a in self.content)
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
        self.assertIn('Where should I write', self.content)
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


SKILL_PATH = os.path.join(os.path.dirname(__file__), "..", "SKILL.md")


def main():
    """Run all compliance checks and print results.

    Loads SKILL.md, runs every test_* function, aggregates pass/fail
    counts, and exits with code 0 only if all tests pass.
    """
    skill_path = SKILL_PATH

    with open(skill_path, "r", encoding="utf-8") as f:
        content = f.read()

    total_passed = 0
    total_failed = 0

    p, f = test_structural(content, skill_path)
    total_passed += p
    total_failed += f

    p, f = test_command_frontmatter(content)
    total_passed += p
    total_failed += f

    p, f = test_required_sections(content)
    total_passed += p
    total_failed += f

    p, f = test_content_quality(content)
    total_passed += p
    total_failed += f

    p, f = test_cross_platform(content)
    total_passed += p
    total_failed += f

    p, f = test_fix_plan(content)
    total_passed += p
    total_failed += f

    p, f = test_baseline_failure_coverage(content)
    total_passed += p
    total_failed += f

    p, f = test_non_negotiable_rules(content)
    total_passed += p
    total_failed += f

    p, f = test_anti_rationalization(content)
    total_passed += p
    total_failed += f

    p, f = test_red_flags(content)
    total_passed += p
    total_failed += f

    p, f = test_integration_discovery_phase(content)
    total_passed += p
    total_failed += f

    p, f = test_integration_parallel_analysis(content)
    total_passed += p
    total_failed += f

    p, f = test_integration_synthesis_roadmap(content)
    total_passed += p
    total_failed += f

    p, f = test_integration_output_cleanup(content)
    total_passed += p
    total_failed += f

    p, f = test_integration_fix_plan(content)
    total_passed += p
    total_failed += f

    p, f = test_integration_safety(content)
    total_passed += p
    total_failed += f

    p, f = test_integration_cross_platform(content)
    total_passed += p
    total_failed += f

    print("\n================================")
    color = "\033[92m" if total_failed == 0 else "\033[91m"
    print(f"{color}Results: {total_passed} passed, {total_failed} failed\033[0m")
    print("================================")

    if total_failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
