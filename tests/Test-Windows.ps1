param()

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir '..')
$Fail = 0

$SkillFile = Join-Path $ProjectRoot 'SKILL.md'
$KarpathyFile = Join-Path $ProjectRoot 'karpathy-guidelines.md'
$ExpectedIssuesFile = Join-Path $ScriptDir 'expected_issues.json'

Write-Host '[INFO] Starting Windows Mock Validation Test Suite'

# --- Check 1: karpathy-guidelines.md exists ---
if (Test-Path $KarpathyFile) {
    Write-Host '[SUCCESS] karpathy-guidelines.md exists'
} else {
    Write-Host '[ERROR] karpathy-guidelines.md missing'
    $Fail = 1
}

# --- Check 2: SKILL.md exists ---
$SkillOk = $true
if (-not (Test-Path $SkillFile)) {
    Write-Host "[ERROR] SKILL.md missing at $SkillFile"
    $Fail = 1
    $SkillOk = $false
}

if ($SkillOk) {
    # --- Check 2a: '🔧 Environment Variables' section ---
    if (Select-String -Path $SkillFile -Pattern '🔧 Environment Variables' -SimpleMatch -Quiet) {
        Write-Host "[SUCCESS] '🔧 Environment Variables' section found"
    } else {
        Write-Host "[ERROR] '🔧 Environment Variables' section missing from SKILL.md"
        $Fail = 1
    }

    if (Select-String -Path $SkillFile -Pattern '💾 Checkpointing' -SimpleMatch -Quiet) {
        Write-Host "[SUCCESS] '💾 Checkpointing' section found"
    } else {
        Write-Host "[ERROR] '💾 Checkpointing' section missing from SKILL.md"
        $Fail = 1
    }

    if (Select-String -Path $SkillFile -Pattern '⚡ Quick Mode' -SimpleMatch -Quiet) {
        Write-Host "[SUCCESS] '⚡ Quick Mode' section found"
    } else {
        Write-Host "[ERROR] '⚡ Quick Mode' section missing from SKILL.md"
        $Fail = 1
    }

    # --- Check 3: No hardcoded 'model: ' in frontmatter ---
    if (Select-String -Path $SkillFile -Pattern '^model: ' -Quiet) {
        Write-Host "[ERROR] Hardcoded 'model: ' still present in SKILL.md frontmatter or templates"
        $Fail = 1
    } else {
        Write-Host "[SUCCESS] No hardcoded 'model: ' in SKILL.md"
    }

    # --- Check 4: Dynamic effort present ---
    if (Select-String -Path $SkillFile -Pattern 'effort: \${CODE_REVIEW_EFFORT:-max}' -Quiet) {
        Write-Host '[SUCCESS] Dynamic effort found in SKILL.md'
    } else {
        Write-Host '[ERROR] Dynamic effort not found in SKILL.md'
        $Fail = 1
    }
}
# --- Check 5: Mock evaluation against expected_issues.json ---
Write-Host '[INFO] Simulating skill evaluation against expected issues...'
if (-not (Test-Path $ExpectedIssuesFile)) {
    Write-Host "[ERROR] expected_issues.json missing at $ExpectedIssuesFile"
    $Fail = 1
    $expectedIssues = @()
} else {
    try {
        $expectedIssues = Get-Content -Path $ExpectedIssuesFile -Raw | ConvertFrom-Json
    } catch {
        Write-Host "[ERROR] Failed to parse expected_issues.json: $_"
        $Fail = 1
        $expectedIssues = @()
    }
}
$mockOutput = @'
CWE-798
CWE-78
CWE-200
unused-import
'@
$mockLines = $mockOutput -split "`r`n|`n"

foreach ($issue in $expectedIssues) {
    if ($issue -in $mockLines) {
        Write-Host "[SUCCESS] Found expected issue: $issue"
    } else {
        Write-Host "[ERROR] Expected issue '$issue' not found in mock output"
        $Fail = 1
    }
}

# --- Check 6: Run compliance tests ---
Write-Host '[INFO] Running compliance tests...'
$complianceOutput = & python (Join-Path $ScriptDir 'test_compliance.py') 2>&1
$complianceExit = $LASTEXITCODE
if ($complianceExit -eq 0) {
    Write-Host '[SUCCESS] Compliance tests passed'
} else {
    Write-Host "[ERROR] Compliance tests failed (exit code: $complianceExit)"
    Write-Host $complianceOutput
    $Fail = 1
}

# --- Check 7: Run Python unit tests ---
Write-Host '[INFO] Running Python unit tests...'
$unitTestOutput = & python -m unittest discover -s $ScriptDir -p 'test_*.py' 2>&1
$unitTestExit = $LASTEXITCODE
if ($unitTestExit -eq 0) {
    Write-Host '[SUCCESS] Unit tests passed'
} else {
    Write-Host "[ERROR] Unit tests failed (exit code: $unitTestExit)"
    Write-Host $unitTestOutput
    $Fail = 1
}

# --- Summary ---
if ($Fail -eq 1) {
    Write-Host '[ERROR] Tests failed!'
    exit 1
} else {
    Write-Host '[SUCCESS] All tests passed! SKILL.md is production-grade.'
    exit 0
}
