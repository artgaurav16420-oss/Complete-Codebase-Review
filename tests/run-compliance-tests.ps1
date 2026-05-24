# Compliance test runner for complete-codebase-review skill
$skillPath = "$PSScriptRoot\..\SKILL.md"
$Pass = 0; $Fail = 0

function Assert-TestResult {
    param([string]$Test, [scriptblock]$Block)
    try {
        if (& $Block) { Write-Host "PASS: $Test" -ForegroundColor Green; $script:Pass++ }
        else { Write-Host "FAIL: $Test" -ForegroundColor Red; $script:Fail++ }
    } catch { Write-Host "FAIL: $Test - $_" -ForegroundColor Red; $script:Fail++ }
}

$content = Get-Content $skillPath -Raw
$lines = Get-Content $skillPath

Write-Host "=== Structural ===" -ForegroundColor Cyan
Assert-TestResult "SKILL.md exists" { Test-Path $skillPath }
Assert-TestResult "Has YAML frontmatter" { $content -match '(?s)^---\r?\n.+\r?\n---' }
Assert-TestResult "Has name" { $content -match '(?m)^name: ' }
Assert-TestResult "Description starts with Use when" { $content -match 'description: Use when' }
Assert-TestResult "No workflow summary in description" {
    $desc = ($content -split "`n" | Where-Object { $_ -match 'description: ' } | Select-Object -First 1)
    $desc -notmatch '(spawn|synthes|phase|agent|parallel)'
}
Assert-TestResult "Has version field" { $content -match '(?m)^version: ' }

Write-Host "=== Command Frontmatter ===" -ForegroundColor Cyan
Assert-TestResult "Has user-invocable: true" { $content -match 'user-invocable: true' }
Assert-TestResult "Has argument-hint" { $content -match 'argument-hint:' }
Assert-TestResult "Has allowed-tools" { $content -match 'allowed-tools:' }
Assert-TestResult "Has allowed-tools including Task" { $content -match 'allowed-tools:' -and $content -match 'Task' }
# disable-model-invocation intentionally absent — skill uses Task agents requiring model invocation
Assert-TestResult "Has dynamic effort via env var" { $content -match 'effort: \$\{CODE_REVIEW_EFFORT:-max\}' }
Assert-TestResult "No hardcoded model pin" { $content -notmatch '(?m)^model: opus' }
Assert-TestResult "References \$ARGUMENTS" { $content -match '\$ARGUMENTS' }
Assert-TestResult "Sets \$TARGET_DIR from args" { $content -match '\$TARGET_DIR' }

Write-Host "=== Required Sections ===" -ForegroundColor Cyan
@(
    "## Overview", "## When to Use", "## Phase 1", "## Phase 2", "## Phase 3",
    "Non-Negotiable Rules", "Anti-Rationalization", "Red Flags",
    "Output Format", "Graceful Degradation", "Common Mistakes",
    "Cross-Boundary", "Specialist Agents", "Web Verification",
    "Cross-platform", "Cleanup", "Environment Variables", "Quick Mode", "Checkpointing"
) | ForEach-Object {
    $name = $_; Assert-TestResult "Has section: $name" { $content -match [regex]::Escape($name) }
}

Write-Host "=== Content Quality ===" -ForegroundColor Cyan
Assert-TestResult "Mentions devil's advocate" { $content -match 'devil.s advocate' }
Assert-TestResult "Mentions CONFIRMED" { $content -match 'CONFIRMED' }
Assert-TestResult "Has specialist agent table" { $content -match 'Architecture Analyzer' -and $content -match 'Security Posture' }
Assert-TestResult "Has at least 12 specialist agents" {
    $agents = @("Architecture Analyzer","Code Quality","Security Posture","Tech Debt","Test Health",
      "Dependency Auditor","Documentation","Build. CI","Performance","Database","DevOps","Standards","UI/UX")
    $matched = ($agents | Where-Object { $content -match $_ }).Count
    $matched -ge 12
}
Assert-TestResult "Has UI/UX Auditor agent" { $content -match 'UI/UX Auditor' }
Assert-TestResult "Requires skill loading per agent" { $content -match 'Load a relevant skill' -and $content -match 'Skill tool' }
Assert-TestResult "Has Discovery phase" { $content -match 'Discovery' }
Assert-TestResult "Has Roadmap phase" { $content -match 'Roadmap' -or $content -match 'roadmap' }
Assert-TestResult "Has tech debt quantification" { $content -match 'tech debt' -or $content -match 'Tech Debt' }
Assert-TestResult "Has health score" { $content -match 'health' -or $content -match 'Health' }
Assert-TestResult "Has phased roadmap" { $content -match 'Phase 1' -and $content -match 'Phase 2' }
Assert-TestResult "Blocks passive monitoring" { $content -match 'do nothing else' -or $content -match 'No messages, no drafting, no polling' }
Assert-TestResult "Blocks partial results" { $content -match 'ALL N' -or $content -match 'all N' }
Assert-TestResult "Has graceful degradation for agent failure" { $content -match 'Agent fail' -or $content -match 'crash' }
Assert-TestResult "Has web verification section" { $content -match '## Web Verification' }
Assert-TestResult "Has cleanup phase" { $content -match 'Cleanup' }
Assert-TestResult "Has output destination ask" { $content -match 'Ask user' -or $content -match 'AskUserQuestion' -or $content -match 'Where should I write' }
Assert-TestResult "Mentions UNVERIFIED" { $content -match 'UNVERIFIED' }
Assert-TestResult "Has sample output section" { $content -match 'Sample Output' -or $content -match 'Example Report' }
Assert-TestResult "Has changelog section" { $content -match 'Changelog' -or $content -match 'Change Log' }

Write-Host "=== Cross-Platform ===" -ForegroundColor Cyan
Assert-TestResult "Has cross-platform directory commands" { $content -match 'Get-ChildItem' -and $content -match 'find' }
Assert-TestResult "Has OS detection" { $content -match '\$IsWindows' -or $content -match 'uname' }
Assert-TestResult "Has cross-platform temp directory" { $content -match '\$env:TEMP' -or $content -match '\$TMPDIR' }
Assert-TestResult "Has git-aware discovery" { $content -match 'git' -and ($content -match 'churn' -or $content -match 'history') }
Assert-TestResult "Has cross-agent conflict resolution" { $content -match 'cross-agent' -or $content -match 'conflict' }
Assert-TestResult "Has DA verdict in output format" { $content -match 'DA Verdict' -or $content -match 'CONFIRMED' }
Assert-TestResult "Declares READ-ONLY" { $content -match 'NEVER modifies the codebase' -or $content -match 'read.only' }

Write-Host "=== Fix Plan ===" -ForegroundColor Cyan
Assert-TestResult "Has Phase 4 section" { $content -match '## Phase 4' }
Assert-TestResult "Has fix plan table" { $content -match 'Task ID' -and $content -match 'T-001' }
Assert-TestResult "Asks user for approval" { $content -match 'Do NOT apply' -and $content -match 'user explicitly' }
Assert-TestResult "Only applies on approved Task IDs" { $content -match 'Task IDs' -or $content -match '"all"' }
Assert-TestResult "Has post-fix verification phase" { $content -match 'Phase 4g' -or $content -match 'Verify Fixes' }

Write-Host "=== Baseline Failure Coverage ===" -ForegroundColor Cyan
Assert-TestResult "Covers shallow scan failure" { $content -match 'Discovery' -and $content -match 'Specialist Agents' }
Assert-TestResult "Covers single-pass bias failure" { $content -match '75%' -or $content -match 'halt if fewer' -or ($content -match 'parallel' -and $content -match 'complete') }
Assert-TestResult "Covers no-structure failure" { $content -match 'Per-Domain' -and $content -match 'severity' }
Assert-TestResult "Covers inconsistent depth failure" { $content -match 'Prioritize core' -and $content -match 'not analyzed' }
Assert-TestResult "Covers no-quantification failure" { $content -match 'quantified metric' -or $content -match 'quantified' }
Assert-TestResult "Covers no-roadmap failure" { $content -match 'Phase 1' -and $content -match 'Phase 2' -and $content -match 'Phase 3' }

Write-Host "=== Non-Negotiable Rules ===" -ForegroundColor Cyan
Assert-TestResult "Has at least 10 rules" { ($lines | Where-Object { $_ -match '^\|\s*\d+\s*\|' }).Count -ge 10 }
Assert-TestResult "Rule 1: Dynamic timeout per agent" { $content -match '\$\{CODE_REVIEW_TIMEOUT_SEC:-900\}' -and $content -match '75%' }
Assert-TestResult "Rule 8: Web verification mandatory" { $content -match 'Web verification MANDATORY' }
Assert-TestResult "Rule 9: NEVER modify codebase" { $content -match 'NEVER modify the codebase' }
Assert-TestResult "Rule 10: Fix plan waits for approval" { $content -match 'MUST wait for user approval' }

Write-Host "=== Anti-Rationalization ===" -ForegroundColor Cyan
Assert-TestResult "Has at least 6 entries" { ($lines | Where-Object { $_ -match '^\| \".+ | \".+' }).Count -ge 6 }
Assert-TestResult "Has web verification rationalization" { $content -match 'Web verification takes too long' }

Write-Host "=== Red Flags ===" -ForegroundColor Cyan
Assert-TestResult "Has at least 5 red flags" { ($lines | Where-Object { $_ -match '^- ' } | Where-Object { $_ -notmatch 'User' -and $_ -notmatch 'source' -and $_ -notmatch 'title' -and $_ -notmatch 'rubric' }).Count -ge 5 }
Assert-TestResult "Stops on insufficient agent coverage" { $content -match '75%' -or $content -match 'insufficient coverage' }
Assert-TestResult "Stops on skipped web verification" { $content -match 'Skipping web verification' }
Assert-TestResult "Stops on modifying files" { $content -match 'Modifying any codebase file' }

Write-Host "`n================================"
Write-Host "Results: $Pass passed, $Fail failed" -ForegroundColor $(if ($fail -eq 0) { "Green" } else { "Red" })
Write-Host "================================"
if ($Fail -gt 0) { exit 1 }
