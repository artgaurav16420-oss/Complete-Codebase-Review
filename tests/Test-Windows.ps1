$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir '..')
$Fail = 0

$SkillFile = Join-Path $ProjectRoot 'SKILL.md'
$KarpathyFile = Join-Path $ProjectRoot 'karpathy-guidelines.md'

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
    # --- Check 2a: 'Environment Variables' section (ASCII match) ---
    if (Select-String -Path $SkillFile -Pattern 'Environment Variables' -SimpleMatch -Quiet) {
        Write-Host "[SUCCESS] 'Environment Variables' section found"
    } else {
        Write-Host "[ERROR] 'Environment Variables' section missing from SKILL.md"
        $Fail = 1
    }

    if (Select-String -Path $SkillFile -Pattern 'Checkpointing' -SimpleMatch -Quiet) {
        Write-Host "[SUCCESS] 'Checkpointing' section found"
    } else {
        Write-Host "[ERROR] 'Checkpointing' section missing from SKILL.md"
        $Fail = 1
    }

    if (Select-String -Path $SkillFile -Pattern 'Quick Mode' -SimpleMatch -Quiet) {
        Write-Host "[SUCCESS] 'Quick Mode' section found"
    } else {
        Write-Host "[ERROR] 'Quick Mode' section missing from SKILL.md"
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
# --- Check 5: Generated docs are current ---
Write-Host '[INFO] Checking generated docs are current...'
python (Join-Path $ProjectRoot 'tools\generate.py') --check
if ($LASTEXITCODE -eq 0) {
    Write-Host '[SUCCESS] Generated docs are current'
} else {
    Write-Host '[ERROR] Generated docs are stale — run: python tools/generate.py'
    $Fail = 1
}

# --- Check 6: Eval harness against recorded fixtures ---
Write-Host '[INFO] Running eval harness...'
python -m ccr eval
if ($LASTEXITCODE -eq 0) {
    Write-Host '[SUCCESS] Eval harness covered all expected issues'
} else {
    Write-Host "[ERROR] Eval harness missed expected issues (exit code: $LASTEXITCODE)"
    $Fail = 1
}

# --- Check 7: Run compliance tests ---
Write-Host '[INFO] Running compliance tests...'
python (Join-Path $ScriptDir 'compliance_test.py')
$complianceExit = $LASTEXITCODE
python (Join-Path $ScriptDir 'review_compliance_test.py')
$reviewComplianceExit = $LASTEXITCODE
if ($complianceExit -eq 0 -and $reviewComplianceExit -eq 0) {
    Write-Host '[SUCCESS] Compliance tests passed'
} else {
    Write-Host "[ERROR] Compliance tests failed (exit codes: $complianceExit, $reviewComplianceExit)"
    $Fail = 1
}

# --- Check 8: Run Python unit tests ---
Write-Host '[INFO] Running Python unit tests...'
python -m unittest discover -s $ScriptDir -p 'test_*.py'
$unitTestExit = $LASTEXITCODE
if ($unitTestExit -eq 0) {
    Write-Host '[SUCCESS] Unit tests passed'
} else {
    Write-Host "[ERROR] Unit tests failed (exit code: $unitTestExit)"
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
