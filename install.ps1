#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Installs the Complete Codebase Review skill for Claude Code.
.DESCRIPTION
    Copies SKILL.md and tests/ to the correct location under ~/.claude/skills/
    so Claude Code can load the skill on invocation.
#>

$skillName = "complete-codebase-review"
$src = Split-Path -Parent $PSCommandPath

# Resolve target directory
$target = if ($IsWindows -or $env:OS -match "Windows") {
    Join-Path $env:USERPROFILE ".claude\skills\$skillName"
} else {
    "$HOME/.claude/skills/$skillName"
}

Write-Host "Installing $skillName to $target ..." -ForegroundColor Cyan

# Create directories
New-Item -ItemType Directory -Path $target -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $target "tests") -Force | Out-Null

# Copy files
Copy-Item -Path (Join-Path $src "SKILL.md") -Destination (Join-Path $target "SKILL.md") -Force
Copy-Item -Path (Join-Path $src "tests\*") -Destination (Join-Path $target "tests\") -Force

# Verify
$skillFile = Join-Path $target "SKILL.md"
if (Test-Path $skillFile) {
    $lines = (Get-Content $skillFile).Count
    Write-Host " Installed: $skillFile ($lines lines)" -ForegroundColor Green
    Write-Host " Invoke with: /complete-codebase-review [path]" -ForegroundColor Green
} else {
    Write-Host " Install failed: $skillFile not found" -ForegroundColor Red
    exit 1
}
