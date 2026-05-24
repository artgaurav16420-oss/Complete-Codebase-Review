# Integration tests for complete-codebase-review skill
# These test the expected behavior patterns (not a live agent run)
$skillPath = Join-Path $PSScriptRoot "..\SKILL.md"
$pass = 0; $fail = 0

function Check {
    param([string]$Test, [scriptblock]$Block)
    try {
        if (& $Block) { Write-Host "PASS: $Test" -ForegroundColor Green; $script:pass++ }
        else { Write-Host "FAIL: $Test" -ForegroundColor Red; $script:fail++ }
    } catch { Write-Host "FAIL: $Test - $_" -ForegroundColor Red; $script:fail++ }
}

$content = Get-Content $skillPath -Raw

Write-Host "=== Integration: Discovery Phase ===" -ForegroundColor Cyan

Check "Discovery collects languages" { $content -match 'Languages' -and $content -match 'Frameworks' }
Check "Discovery collects git history" { $content -match 'git' -and $content -match 'churn' }
Check "Discovery writes manifest" { $content -match 'Write.*manifest' -or $content -match 'ccr-manifest' }
Check "Discovery has health dimension table" { $content -match 'Architecture & Design' -and $content -match 'Security Posture' }
Check "Discovery selects dimensions by criteria" { $content -match 'Applies When' }
Check "Discovery verifies cache access first" { $content -match 'Verify Cache Access' }

Write-Host "=== Integration: Parallel Analysis ===" -ForegroundColor Cyan

Check "All 13 agents have unique coverage" {
    $agents = @(
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
        "Standards Compliance"
    )
    ($agents | Where-Object { $content -match $_ }).Count -ge 13
}
Check "Each agent has methodology requirement" { $content -match 'Methodology' -and $content -match 'Step-by-step' }
Check "Each agent must quantify findings" { $content -match 'Quantify findings' -or $content -match 'Quantification' }
Check "Each agent must web verify" { $content -match 'Web Verify' }
Check "Each agent loads a skill" { $content -match 'Load a relevant skill' -and $content -match 'Skill tool' }
Check "Parallel orchestration is passive" { $content -match 'do nothing else' -and $content -match 'No messages, no drafting, no polling' }
Check "Task invocation example provided" { $content -match 'task name:' -or $content -match 'subagent_type:' }

Write-Host "=== Integration: Synthesis + Roadmap ===" -ForegroundColor Cyan

Check "Synthesis deduplicates findings" { $content -match 'Deduplicate' }
Check "Synthesis normalizes severity" { $content -match 'Normalize severity' }
Check "Synthesis resolves cross-agent conflicts" { $content -match 'cross-agent' -or $content -match 'conflict' }
Check "Synthesis quantifies tech debt" { $content -match 'Quantify tech debt' }
Check "Roadmap has 3 phases" { $content -match 'Phase 1' -and $content -match 'Phase 2' -and $content -match 'Phase 3' }
Check "Roadmap prioritizes by impact vs effort" { $content -match 'impact vs effort' }
Check "DA challenges every finding" { $content -match 'Challenge EVERY' }
Check "DA web-verifies claims" { $content -match 'Web-verify each claim' }
Check "DA independently reads code" { $content -match 'Independently read code' }
Check "DA uses CONFIRMED/PLAUSIBLE/QUESTIONABLE/REJECTED" { $content -match 'CONFIRMED' -and $content -match 'PLAUSIBLE' -and $content -match 'QUESTIONABLE' -and $content -match 'REJECTED' }

Write-Host "=== Integration: Output + Cleanup ===" -ForegroundColor Cyan

Check "Asks user for output destination" { $content -match 'Where should I write' }
Check "Deletes temp files after output" { $content -match 'Delete' -and $content -match 'cache' }
Check "Health report has executive summary" { $content -match 'Executive Summary' }
Check "Health report has per-domain scores" { $content -match 'Per-Domain Scores' }
Check "Health report has DA verdict column" { $content -match 'DA Verdict' }

Write-Host "=== Integration: Fix Plan ===" -ForegroundColor Cyan

Check "Fix plan generates tasks with IDs" { $content -match 'Task ID' -and $content -match 'T-001' }
Check "Fix plan requires user approval" { $content -match 'Do NOT apply' -and $content -match 'user explicitly' }
Check "Fix plan supports selective approval" { $content -match 'Task IDs' }
Check "Fix plan supports 'all' shortcut" { $content -match '"all"' }
Check "Fix plan supports 'skip' to exit" { $content -match 'skip' }
Check "Applies CRITICAL before HIGH" { $content -match 'CRITICAL items first' }
Check "Has baseline snapshot for trend" { $content -match 'baseline' -and $content -match 'trend' }
Check "Has re-review guidance" { $content -match 'Re-review' -or $content -match 'follow-up' }
Check "Has post-fix verification step" { $content -match 'Verify Fixes' -or $content -match 'Phase 4g' }

Write-Host "=== Integration: Safety ===" -ForegroundColor Cyan

Check "Declares READ-ONLY" { $content -match 'NEVER modify the codebase' -or $content -match 'READ-ONLY' }
Check "Rule 9: no codebase modification" { $content -match 'NEVER modify the codebase during Phases 1-3' }
Check "Rule 10: no auto-apply" { $content -match 'MUST wait for user approval' }
Check "Red flag for modifying files" { $content -match 'Modifying any codebase file' }
Check "Red flag for auto-apply" { $content -match 'without explicit user approval' }

Write-Host "=== Integration: Cross-Platform ===" -ForegroundColor Cyan

Check "Detects OS" { $content -match '$IsWindows' -or $content -match 'uname' }
Check "Windows commands available" { $content -match 'Get-ChildItem' }
Check "Unix commands available" { $content -match 'find' }
Check "Temp dir fallback" { $content -match 'Fall back to OS temporary directory' }

Write-Host "
================================"
Write-Host "Results: $pass passed, $fail failed" -ForegroundColor $(if ($fail -eq 0) { "Green" } else { "Red" })
Write-Host "================================"
if ($fail -gt 0) { exit 1 }
