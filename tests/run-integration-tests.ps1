# Integration tests for complete-codebase-review skill
# These test the expected behavior patterns (not a live agent run)
$skillPath = Join-Path $PSScriptRoot "..\SKILL.md"
$Pass = 0; $Fail = 0

function Assert-TestResult {
    param([string]$Test, [scriptblock]$Block)
    try {
        if (& $Block) { Write-Host "PASS: $Test" -ForegroundColor Green; $script:Pass++ }
        else { Write-Host "FAIL: $Test" -ForegroundColor Red; $script:Fail++ }
    } catch { Write-Host "FAIL: $Test - $_" -ForegroundColor Red; $script:Fail++ }
}

$content = Get-Content $skillPath -Raw

Write-Host "=== Integration: Discovery Phase ===" -ForegroundColor Cyan

Assert-TestResult "Discovery collects languages" { $content -match 'Languages' -and $content -match 'Frameworks' }
Assert-TestResult "Discovery collects git history" { $content -match 'git' -and $content -match 'churn' }
Assert-TestResult "Discovery writes manifest" { $content -match 'Write.*manifest' -or $content -match 'ccr-manifest' }
Assert-TestResult "Discovery has health dimension table" { $content -match 'Architecture & Design' -and $content -match 'Security Posture' }
Assert-TestResult "Discovery selects dimensions by criteria" { $content -match 'Applies When' }
Assert-TestResult "Discovery verifies cache access first" { $content -match 'Verify Cache Access' }

Write-Host "=== Integration: Parallel Analysis ===" -ForegroundColor Cyan

Assert-TestResult "All 13 agents have unique coverage" {
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
Assert-TestResult "Each agent has methodology requirement" { $content -match 'Methodology' -and $content -match 'Step-by-step' }
Assert-TestResult "Each agent must quantify findings" { $content -match 'Quantify findings' -or $content -match 'Quantification' }
Assert-TestResult "Each agent must web verify" { $content -match 'Web Verify' }
Assert-TestResult "Each agent loads a skill" { $content -match 'Load a relevant skill' -and $content -match 'Skill tool' }
Assert-TestResult "Parallel orchestration is passive" { $content -match 'do nothing else' -and $content -match 'No messages, no drafting, no polling' }
Assert-TestResult "Task invocation example provided" { $content -match 'task name:' -or $content -match 'subagent_type:' }

Write-Host "=== Integration: Synthesis + Roadmap ===" -ForegroundColor Cyan

Assert-TestResult "Synthesis deduplicates findings" { $content -match 'Deduplicate' }
Assert-TestResult "Synthesis normalizes severity" { $content -match 'Normalize severity' }
Assert-TestResult "Synthesis resolves cross-agent conflicts" { $content -match 'cross-agent' -or $content -match 'conflict' }
Assert-TestResult "Synthesis quantifies tech debt" { $content -match 'Quantify tech debt' }
Assert-TestResult "Roadmap has 3 phases" { $content -match 'Phase 1' -and $content -match 'Phase 2' -and $content -match 'Phase 3' }
Assert-TestResult "Roadmap prioritizes by impact vs effort" { $content -match 'impact vs effort' }
Assert-TestResult "DA challenges every finding" { $content -match 'Challenge EVERY' }
Assert-TestResult "DA web-verifies claims" { $content -match 'Web-verify each claim' }
Assert-TestResult "DA independently reads code" { $content -match 'Independently read code' }
Assert-TestResult "DA uses CONFIRMED/PLAUSIBLE/QUESTIONABLE/REJECTED" { $content -match 'CONFIRMED' -and $content -match 'PLAUSIBLE' -and $content -match 'QUESTIONABLE' -and $content -match 'REJECTED' }

Write-Host "=== Integration: Output + Cleanup ===" -ForegroundColor Cyan

Assert-TestResult "Asks user for output destination" { $content -match 'Where should I write' }
Assert-TestResult "Deletes temp files after output" { $content -match 'Delete' -and $content -match 'cache' }
Assert-TestResult "Health report has executive summary" { $content -match 'Executive Summary' }
Assert-TestResult "Health report has per-domain scores" { $content -match 'Per-Domain Scores' }
Assert-TestResult "Health report has DA verdict column" { $content -match 'DA Verdict' }

Write-Host "=== Integration: Fix Plan ===" -ForegroundColor Cyan

Assert-TestResult "Fix plan generates tasks with IDs" { $content -match 'Task ID' -and $content -match 'T-001' }
Assert-TestResult "Fix plan requires user approval" { $content -match 'Do NOT apply' -and $content -match 'user explicitly' }
Assert-TestResult "Fix plan supports selective approval" { $content -match 'Task IDs' }
Assert-TestResult "Fix plan supports 'all' shortcut" { $content -match '"all"' }
Assert-TestResult "Fix plan supports 'skip' to exit" { $content -match 'skip' }
Assert-TestResult "Applies CRITICAL before HIGH" { $content -match 'CRITICAL items first' }
Assert-TestResult "Has baseline snapshot for trend" { $content -match 'baseline' -and $content -match 'trend' }
Assert-TestResult "Has re-review guidance" { $content -match 'Re-review' -or $content -match 'follow-up' }
Assert-TestResult "Has post-fix verification step" { $content -match 'Verify Fixes' -or $content -match 'Phase 4g' }

Write-Host "=== Integration: Safety ===" -ForegroundColor Cyan

Assert-TestResult "Declares READ-ONLY" { $content -match 'NEVER modify the codebase' -or $content -match 'READ-ONLY' }
Assert-TestResult "Rule 9: no codebase modification" { $content -match 'NEVER modify the codebase during Phases 1-3' }
Assert-TestResult "Rule 10: no auto-apply" { $content -match 'MUST wait for user approval' }
Assert-TestResult "Red flag for modifying files" { $content -match 'Modifying any codebase file' }
Assert-TestResult "Red flag for auto-apply" { $content -match 'without explicit user approval' }

Write-Host "=== Integration: Cross-Platform ===" -ForegroundColor Cyan

Assert-TestResult "Detects OS" { $content -match '$IsWindows' -or $content -match 'uname' }
Assert-TestResult "Windows commands available" { $content -match 'Get-ChildItem' }
Assert-TestResult "Unix commands available" { $content -match 'find' }
Assert-TestResult "Temp dir fallback" { $content -match 'Fall back to OS temporary directory' }

Write-Host "
================================"
Write-Host "Results: $Pass passed, $Fail failed" -ForegroundColor $(if ($fail -eq 0) { "Green" } else { "Red" })
Write-Host "================================"
if ($Fail -gt 0) { exit 1 }
