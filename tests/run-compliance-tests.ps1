# Compliance test runner for complete-codebase-review skill
$skillPath = "$PSScriptRoot\..\SKILL.md"
$pass = 0; $fail = 0

function Check {
    param([string]$Test, [scriptblock]$Block)
    try {
        if (& $Block) { Write-Host "PASS: $Test" -ForegroundColor Green; $script:pass++ }
        else { Write-Host "FAIL: $Test" -ForegroundColor Red; $script:fail++ }
    } catch { Write-Host "FAIL: $Test - $_" -ForegroundColor Red; $script:fail++ }
}

$content = Get-Content $skillPath -Raw
$lines = Get-Content $skillPath

Write-Host "=== Structural ===" -ForegroundColor Cyan
Check "SKILL.md exists" { Test-Path $skillPath }
Check "Has YAML frontmatter" { $content -match '(?s)^---\r?\n.+\r?\n---' }
Check "Has name" { $content -match '(?m)^name: ' }
Check "Description starts with Use when" { $content -match 'description: Use when' }
Check "No workflow summary in description" {
    $desc = ($content -split "`n" | Where-Object { $_ -match 'description: ' } | Select-Object -First 1)
    $desc -notmatch '(spawn|synthes|phase|agent|parallel)'
}

Write-Host "=== Command Frontmatter ===" -ForegroundColor Cyan
Check "Has user-invocable: true" { $content -match 'user-invocable: true' }
Check "Has argument-hint" { $content -match 'argument-hint:' }
Check "Has allowed-tools" { $content -match 'allowed-tools:' }
Check "Has allowed-tools including Task" { $content -match 'allowed-tools:' -and $content -match 'Task' }
# disable-model-invocation intentionally absent — skill uses Task agents requiring model invocation
Check "Has effort: max" { $content -match 'effort: max' }
Check "Has model: opus" { $content -match 'model: opus' }
Check "References \$ARGUMENTS" { $content -match '\$ARGUMENTS' }
Check "Sets \$TARGET_DIR from args" { $content -match '\$TARGET_DIR' }

Write-Host "=== Required Sections ===" -ForegroundColor Cyan
@(
    "## Overview", "## When to Use", "## Phase 1", "## Phase 2", "## Phase 3",
    "Non-Negotiable Rules", "Anti-Rationalization", "Red Flags",
    "Output Format", "Graceful Degradation", "Common Mistakes",
    "Cross-Boundary", "Specialist Agents", "Web Verification",
    "Cross-platform", "Cleanup"
) | ForEach-Object {
    $name = $_; Check "Has section: $name" { $content -match [regex]::Escape($name) }
}

Write-Host "=== Content Quality ===" -ForegroundColor Cyan
Check "Mentions devil's advocate" { $content -match 'devil.s advocate' }
Check "Mentions CONFIRMED" { $content -match 'CONFIRMED' }
Check "Has specialist agent table" { $content -match 'Architecture Analyzer' -and $content -match 'Security Posture' }
Check "Has at least 12 specialist agents" {
    $agents = @("Architecture Analyzer","Code Quality","Security Posture","Tech Debt","Test Health",
      "Dependency Auditor","Documentation","Build. CI","Performance","Database","DevOps","Standards","UI/UX")
    $matched = ($agents | Where-Object { $content -match $_ }).Count
    $matched -ge 12
}
Check "Has UI/UX Auditor agent" { $content -match 'UI/UX Auditor' }
Check "Requires skill loading per agent" { $content -match 'Load a relevant skill' -and $content -match 'Skill tool' }
Check "Has Discovery phase" { $content -match 'Discovery' }
Check "Has Roadmap phase" { $content -match 'Roadmap' -or $content -match 'roadmap' }
Check "Has tech debt quantification" { $content -match 'tech debt' -or $content -match 'Tech Debt' }
Check "Has health score" { $content -match 'health' -or $content -match 'Health' }
Check "Has phased roadmap" { $content -match 'Phase 1' -and $content -match 'Phase 2' }
Check "Blocks passive monitoring" { $content -match 'do nothing else' -or $content -match 'No messages, no drafting, no polling' }
Check "Blocks partial results" { $content -match 'ALL N' -or $content -match 'all N' }
Check "Has graceful degradation for agent failure" { $content -match 'Agent fail' -or $content -match 'crash' }
Check "Has web verification section" { $content -match '## Web Verification' }
Check "Has cleanup phase" { $content -match 'Cleanup' }
Check "Has output destination ask" { $content -match 'Ask user' -or $content -match 'AskUserQuestion' -or $content -match 'Where should I write' }
Check "Mentions UNVERIFIED" { $content -match 'UNVERIFIED' }

Write-Host "=== Cross-Platform ===" -ForegroundColor Cyan
Check "Has cross-platform directory commands" { $content -match 'Get-ChildItem' -and $content -match 'find' }
Check "Has OS detection" { $content -match '\$IsWindows' -or $content -match 'uname' }
Check "Has cross-platform temp directory" { $content -match '\$env:TEMP' -or $content -match '\$TMPDIR' }
Check "Has git-aware discovery" { $content -match 'git' -and ($content -match 'churn' -or $content -match 'history') }
Check "Has estimated duration" { $content -match 'Estimated duration' }
Check "Has cross-agent conflict resolution" { $content -match 'cross-agent' -or $content -match 'conflict' }
Check "Has DA verdict in output format" { $content -match 'DA Verdict' -or $content -match 'CONFIRMED' }
Check "Declares READ-ONLY" { $content -match 'NEVER modifies the codebase' -or $content -match 'read.only' }

Write-Host "=== Fix Plan ===" -ForegroundColor Cyan
Check "Has Phase 4 section" { $content -match '## Phase 4' }
Check "Has fix plan table" { $content -match 'Task ID' -and $content -match 'T-001' }
Check "Asks user for approval" { $content -match 'Do NOT apply' -and $content -match 'user explicitly' }
Check "Only applies on approved Task IDs" { $content -match 'Task IDs' -or $content -match '"all"' }

Write-Host "=== Baseline Failure Coverage ===" -ForegroundColor Cyan
Check "Covers shallow scan failure" { $content -match 'Discovery' -and $content -match 'Specialist Agents' }
Check "Covers single-pass bias failure" { $content -match 'fewer than 8 agents complete' -and $content -match 'parallel' }
Check "Covers no-structure failure" { $content -match 'Per-Domain' -and $content -match 'severity' }
Check "Covers inconsistent depth failure" { $content -match 'Prioritize core' -and $content -match 'not analyzed' }
Check "Covers no-quantification failure" { $content -match 'quantified metric' -or $content -match 'quantified' }
Check "Covers no-roadmap failure" { $content -match 'Phase 1' -and $content -match 'Phase 2' -and $content -match 'Phase 3' }

Write-Host "=== Non-Negotiable Rules ===" -ForegroundColor Cyan
Check "Has at least 9 rules" { ($lines | Where-Object { $_ -match '^\|\s*\d+\s*\|' }).Count -ge 9 }
Check "Rule 1: Wait up to 15 min per agent" { $content -match 'Wait up to 15 minutes per agent' }
Check "Rule 8: Web verification mandatory" { $content -match 'Web verification MANDATORY' }
Check "Rule 9: NEVER modify codebase" { $content -match 'NEVER modify the codebase' }
Check "Rule 10: Fix plan waits for approval" { $content -match 'MUST wait for user approval' }

Write-Host "=== Anti-Rationalization ===" -ForegroundColor Cyan
Check "Has at least 6 entries" { ($lines | Where-Object { $_ -match '^\| \".+ | \".+' }).Count -ge 6 }
Check "Has web verification rationalization" { $content -match 'Web verification takes too long' }

Write-Host "=== Red Flags ===" -ForegroundColor Cyan
Check "Has at least 5 red flags" { ($lines | Where-Object { $_ -match '^- ' } | Where-Object { $_ -notmatch 'User' -and $_ -notmatch 'source' -and $_ -notmatch 'title' -and $_ -notmatch 'rubric' }).Count -ge 5 }
Check "Stops on <=6 agents" { $content -match '≤6 specialist agents' }
Check "Stops on skipped web verification" { $content -match 'Skipping web verification' }
Check "Stops on modifying files" { $content -match 'Modifying any codebase file' }

Write-Host "`n================================"
Write-Host "Results: $pass passed, $fail failed" -ForegroundColor $(if ($fail -eq 0) { "Green" } else { "Red" })
Write-Host "================================"
if ($fail -gt 0) { exit 1 }
