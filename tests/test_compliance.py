import os
import re
import sys

def check(test_name, condition):
    if condition:
        print(f"\033[92mPASS:\033[0m {test_name}")
        return True
    else:
        print(f"\033[91mFAIL:\033[0m {test_name}")
        return False

def test_structural(content, skill_path):
    pass_count = 0
    fail_count = 0
    def run_check(test_name, condition):
        nonlocal pass_count, fail_count
        if check(test_name, condition):
            pass_count += 1
        else:
            fail_count += 1
    print("\033[96m=== Structural ===\033[0m")
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
    return pass_count, fail_count

def test_command_frontmatter(content):
    pass_count = 0
    fail_count = 0
    def run_check(test_name, condition):
        nonlocal pass_count, fail_count
        if check(test_name, condition):
            pass_count += 1
        else:
            fail_count += 1
    print("\033[96m=== Command Frontmatter ===\033[0m")
    run_check("Has user-invocable: true", 'user-invocable: true' in content)
    run_check("Has argument-hint", 'argument-hint:' in content)
    run_check("Has allowed-tools", 'allowed-tools:' in content)
    run_check("Has allowed-tools including Task", 'allowed-tools:' in content and 'Task' in content)
    run_check("Has effort: max", 'effort: ${CODE_REVIEW_EFFORT:-max}' in content)
    run_check("Model: opus is absent", re.search(r'(?m)^model: opus', content) is None)
    run_check("References $ARGUMENTS", '$ARGUMENTS' in content)
    run_check("Sets $TARGET_DIR from args", '$TARGET_DIR' in content)
    return pass_count, fail_count

def test_required_sections(content):
    pass_count = 0
    fail_count = 0
    def run_check(test_name, condition):
        nonlocal pass_count, fail_count
        if check(test_name, condition):
            pass_count += 1
        else:
            fail_count += 1
    print("\033[96m=== Required Sections ===\033[0m")
    sections = [
        "## Overview", "## When to Use", "## Phase 1", "## Phase 2", "## Phase 3",
        "Non-Negotiable Rules", "Anti-Rationalization", "Red Flags",
        "Output Format", "Graceful Degradation", "Common Mistakes",
        "Cross-Boundary", "Specialist Agents", "Web Verification",
        "Cross-platform", "Cleanup"
    ]
    for section in sections:
        run_check(f"Has section: {section}", section in content)
    return pass_count, fail_count

def test_content_quality(content):
    pass_count = 0
    fail_count = 0
    def run_check(test_name, condition):
        nonlocal pass_count, fail_count
        if check(test_name, condition):
            pass_count += 1
        else:
            fail_count += 1
    print("\033[96m=== Content Quality ===\033[0m")
    run_check("Mentions devil's advocate", re.search(r"devil'?s advocate", content, re.IGNORECASE) is not None)
    run_check("Mentions CONFIRMED", 'CONFIRMED' in content)
    run_check("Has specialist agent table", 'Architecture Analyzer' in content and 'Security Posture' in content)

    agents = [
        "Architecture Analyzer", "Code Quality", "Security Posture",
        "Tech Debt", "Test Health", "Dependency Auditor",
        "Documentation", "Build", "CI", "Performance",
        "Database", "DevOps", "Standards", "UI/UX",
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
    return pass_count, fail_count

def test_cross_platform(content):
    pass_count = 0
    fail_count = 0
    def run_check(test_name, condition):
        nonlocal pass_count, fail_count
        if check(test_name, condition):
            pass_count += 1
        else:
            fail_count += 1
    print("\033[96m=== Cross-Platform ===\033[0m")
    run_check("Has cross-platform directory commands", 'Get-ChildItem' in content and 'find' in content)
    run_check("Has OS detection", '$IsWindows' in content or 'uname' in content)
    run_check("Has cross-platform temp directory", '$env:TEMP' in content or '$TMPDIR' in content)
    run_check("Has git-aware discovery", 'git' in content and ('churn' in content or 'history' in content))
    run_check("Has cross-agent conflict resolution", 'cross-agent' in content or 'conflict' in content)
    run_check("Has DA verdict in output format", 'DA Verdict' in content or 'CONFIRMED' in content)
    run_check("Declares READ-ONLY", 'NEVER modifies the codebase' in content or re.search(r'read.only', content, re.IGNORECASE) is not None)
    return pass_count, fail_count

def test_fix_plan(content):
    pass_count = 0
    fail_count = 0
    def run_check(test_name, condition):
        nonlocal pass_count, fail_count
        if check(test_name, condition):
            pass_count += 1
        else:
            fail_count += 1
    print("\033[96m=== Fix Plan ===\033[0m")
    run_check("Has Phase 4 section", '## Phase 4' in content)
    run_check("Has fix plan table", 'Task ID' in content and 'T-001' in content)
    run_check("Asks user for approval", 'Do NOT apply' in content and 'user explicitly' in content)
    run_check("Only applies on approved Task IDs", 'Task IDs' in content or '"all"' in content)
    run_check("Has post-fix verification phase", 'Phase 4g' in content or 'Verify Fixes' in content)
    run_check("Applies CRITICAL before HIGH", 'CRITICAL items first' in content)
    run_check("Has baseline snapshot for trend", 'baseline' in content and 'trend' in content)
    run_check("Has re-review guidance", 'Re-review' in content or 'follow-up' in content)
    return pass_count, fail_count

def test_baseline_failure_coverage(content):
    pass_count = 0
    fail_count = 0
    def run_check(test_name, condition):
        nonlocal pass_count, fail_count
        if check(test_name, condition):
            pass_count += 1
        else:
            fail_count += 1
    print("\033[96m=== Baseline Failure Coverage ===\033[0m")
    run_check("Covers shallow scan failure", 'Discovery' in content and 'Specialist Agents' in content)
    run_check("Covers single-pass bias failure", re.search(r'fewer than \d+% of agents complete', content) is not None or ('fewer than' in content and 'parallel' in content))
    run_check("Covers no-structure failure", 'Per-Domain' in content and 'severity' in content)
    run_check("Covers inconsistent depth failure", 'Prioritize core' in content and 'not analyzed' in content)
    run_check("Covers no-quantification failure", 'quantified metric' in content or 'quantified' in content)
    run_check("Covers no-roadmap failure", 'Phase 1' in content and 'Phase 2' in content and 'Phase 3' in content)
    return pass_count, fail_count

def test_non_negotiable_rules(content):
    pass_count = 0
    fail_count = 0
    def run_check(test_name, condition):
        nonlocal pass_count, fail_count
        if check(test_name, condition):
            pass_count += 1
        else:
            fail_count += 1
    print("\033[96m=== Non-Negotiable Rules ===\033[0m")
    rule_lines = [line for line in content.split('\n') if re.match(r'^\|\s*\d+\s*\|', line)]
    run_check("Has at least 10 rules", len(rule_lines) >= 10)
    run_check("Rule 1: Dynamic timeout per agent + 75% threshold", re.search(r'\$\{CODE_REVIEW_TIMEOUT_SEC:-900\}', content) is not None and '75%' in content)
    run_check("Rule 8: Web verification mandatory", 'Web verification MANDATORY' in content)
    run_check("Rule 9: NEVER modify codebase", 'NEVER modify the codebase' in content)
    run_check("Rule 10: Fix plan waits for approval", 'MUST wait for user approval' in content)
    return pass_count, fail_count

def test_anti_rationalization(content):
    pass_count = 0
    fail_count = 0
    def run_check(test_name, condition):
        nonlocal pass_count, fail_count
        if check(test_name, condition):
            pass_count += 1
        else:
            fail_count += 1
    print("\033[96m=== Anti-Rationalization ===\033[0m")
    anti_rat_lines = [line for line in content.split('\n') if re.match(r'^\| ".+ | ".+', line)]
    run_check("Has at least 6 entries", len(anti_rat_lines) >= 6)
    run_check("Has web verification rationalization", 'Web verification takes too long' in content)
    return pass_count, fail_count

def test_red_flags(content):
    pass_count = 0
    fail_count = 0
    def run_check(test_name, condition):
        nonlocal pass_count, fail_count
        if check(test_name, condition):
            pass_count += 1
        else:
            fail_count += 1
    print("\033[96m=== Red Flags ===\033[0m")
    red_flag_lines = [line for line in content.split('\n') if re.match(r'^- ', line) and not any(x in line for x in ['User', 'source', 'title', 'rubric'])]
    run_check("Has at least 5 red flags", len(red_flag_lines) >= 5)
    run_check("Stops on insufficient agent coverage", '75%' in content or 'insufficient coverage' in content)
    run_check("Stops on skipped web verification", 'Skipping web verification' in content)
    run_check("Stops on modifying files", 'Modifying any codebase file' in content)
    return pass_count, fail_count

def test_integration_discovery_phase(content):
    pass_count = 0
    fail_count = 0
    def run_check(test_name, condition):
        nonlocal pass_count, fail_count
        if check(test_name, condition):
            pass_count += 1
        else:
            fail_count += 1
    print("\033[96m=== Integration: Discovery Phase ===\033[0m")
    run_check("Discovery collects languages", 'Languages' in content and 'Frameworks' in content)
    run_check("Discovery collects git history", 'git' in content and re.search(r'churn|history', content, re.IGNORECASE) is not None)
    run_check("Discovery writes manifest", re.search(r'Write.*manifest', content) is not None or 'ccr-manifest' in content)
    run_check("Discovery has health dimension table", 'Architecture & Design' in content and 'Security Posture' in content)
    run_check("Discovery selects dimensions by criteria", 'Applies When' in content)
    run_check("Discovery has environment check step", 'Environment Check' in content and 'Critical?' in content)
    return pass_count, fail_count

def test_integration_parallel_analysis(content):
    pass_count = 0
    fail_count = 0
    def run_check(test_name, condition):
        nonlocal pass_count, fail_count
        if check(test_name, condition):
            pass_count += 1
        else:
            fail_count += 1
    print("\033[96m=== Integration: Parallel Analysis ===\033[0m")
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
    return pass_count, fail_count

def test_integration_synthesis_roadmap(content):
    pass_count = 0
    fail_count = 0
    def run_check(test_name, condition):
        nonlocal pass_count, fail_count
        if check(test_name, condition):
            pass_count += 1
        else:
            fail_count += 1
    print("\033[96m=== Integration: Synthesis + Roadmap ===\033[0m")
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
    return pass_count, fail_count

def test_integration_output_cleanup(content):
    pass_count = 0
    fail_count = 0
    def run_check(test_name, condition):
        nonlocal pass_count, fail_count
        if check(test_name, condition):
            pass_count += 1
        else:
            fail_count += 1
    print("\033[96m=== Integration: Output + Cleanup ===\033[0m")
    run_check("Asks user for output destination", 'Where should I write' in content)
    run_check("Deletes temp files after output", 'Delete' in content and 'temp' in content)
    run_check("Health report has executive summary", 'Executive Summary' in content)
    run_check("Health report has per-domain scores", 'Per-Domain Scores' in content)
    run_check("Health report has DA verdict column", 'DA Verdict' in content)
    run_check("Has CODE_REVIEW_FILTER env var", 'CODE_REVIEW_FILTER' in content)
    run_check("Filters by critical-high", 'critical-high' in content)
    return pass_count, fail_count

def test_integration_fix_plan(content):
    pass_count = 0
    fail_count = 0
    def run_check(test_name, condition):
        nonlocal pass_count, fail_count
        if check(test_name, condition):
            pass_count += 1
        else:
            fail_count += 1
    print("\033[96m=== Integration: Fix Plan ===\033[0m")
    run_check("Fix plan generates tasks with IDs", 'Task ID' in content and 'T-001' in content)
    run_check("Fix plan requires user approval", 'Do NOT apply' in content and 'user explicitly' in content)
    run_check("Fix plan supports selective approval", 'Task IDs' in content)
    run_check("Fix plan supports 'all' shortcut", '"all"' in content)
    run_check("Fix plan supports 'skip' to exit", 'skip' in content)
    run_check("Applies CRITICAL before HIGH", 'CRITICAL items first' in content)
    run_check("Has baseline snapshot for trend", 'baseline' in content and 'trend' in content)
    run_check("Has re-review guidance", 'Re-review' in content or 'follow-up' in content)
    run_check("EST-CONFLICT logged on estimate variance", 'EST-CONFLICT' in content)
    return pass_count, fail_count

def test_integration_safety(content):
    pass_count = 0
    fail_count = 0
    def run_check(test_name, condition):
        nonlocal pass_count, fail_count
        if check(test_name, condition):
            pass_count += 1
        else:
            fail_count += 1
    print("\033[96m=== Integration: Safety ===\033[0m")
    run_check("Declares READ-ONLY", 'NEVER modify the codebase' in content or 'READ-ONLY' in content)
    run_check("Rule 9: no codebase modification", 'NEVER modify the codebase during Phases 1-3' in content)
    run_check("Rule 10: no auto-apply", 'MUST wait for user approval' in content)
    run_check("Red flag for modifying files", 'Modifying any codebase file' in content)
    run_check("Red flag for auto-apply", 'without explicit user approval' in content)
    return pass_count, fail_count

def test_integration_cross_platform(content):
    pass_count = 0
    fail_count = 0
    def run_check(test_name, condition):
        nonlocal pass_count, fail_count
        if check(test_name, condition):
            pass_count += 1
        else:
            fail_count += 1
    print("\033[96m=== Integration: Cross-Platform ===\033[0m")
    run_check("Detects OS", '$IsWindows' in content or 'uname' in content)
    run_check("Windows commands available", 'Get-ChildItem' in content)
    run_check("Unix commands available", 'find' in content)
    run_check("Temp dir fallback", any(x in content for x in ['$env:TEMP', '$TMPDIR', '/tmp', 'Fall back to OS temporary directory']))
    return pass_count, fail_count

SKILL_PATH = os.path.join(os.path.dirname(__file__), "..", "SKILL.md")


def main():
    skill_path = SKILL_PATH

    with open(skill_path, "r", encoding="utf-8") as f:
        content = f.read()

    total_passed = 0
    total_failed = 0

    p, f = test_structural(content, skill_path)
    total_passed += p; total_failed += f

    p, f = test_command_frontmatter(content)
    total_passed += p; total_failed += f

    p, f = test_required_sections(content)
    total_passed += p; total_failed += f

    p, f = test_content_quality(content)
    total_passed += p; total_failed += f

    p, f = test_cross_platform(content)
    total_passed += p; total_failed += f

    p, f = test_fix_plan(content)
    total_passed += p; total_failed += f

    p, f = test_baseline_failure_coverage(content)
    total_passed += p; total_failed += f

    p, f = test_non_negotiable_rules(content)
    total_passed += p; total_failed += f

    p, f = test_anti_rationalization(content)
    total_passed += p; total_failed += f

    p, f = test_red_flags(content)
    total_passed += p; total_failed += f

    p, f = test_integration_discovery_phase(content)
    total_passed += p; total_failed += f

    p, f = test_integration_parallel_analysis(content)
    total_passed += p; total_failed += f

    p, f = test_integration_synthesis_roadmap(content)
    total_passed += p; total_failed += f

    p, f = test_integration_output_cleanup(content)
    total_passed += p; total_failed += f

    p, f = test_integration_fix_plan(content)
    total_passed += p; total_failed += f

    p, f = test_integration_safety(content)
    total_passed += p; total_failed += f

    p, f = test_integration_cross_platform(content)
    total_passed += p; total_failed += f

    print("\n================================")
    color = "\033[92m" if total_failed == 0 else "\033[91m"
    print(f"{color}Results: {total_passed} passed, {total_failed} failed\033[0m")
    print("================================")

    if total_failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
