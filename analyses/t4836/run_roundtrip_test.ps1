# t/4836 format fix: run the real round-trip test against this worktree's reformatted files
# (Write-PovTaxonomyFile.Tests.ps1:92-102), pointed at this worktree via AI_TRIAD_DATA_ROOT so it
# exercises the new head, not the shared ai-triad-data checkout.
$env:AI_TRIAD_DATA_ROOT = (Get-Location).Path
Import-Module Pester -MinimumVersion 5.0 -ErrorAction Stop
$TestPath = Join-Path $env:USERPROFILE 'repos\ai-triad-research\tests\Write-PovTaxonomyFile.Tests.ps1'
$r = Invoke-Pester -Path $TestPath -PassThru -Output Detailed
Write-Host "TOTAL: Passed=$($r.PassedCount) Failed=$($r.FailedCount)"
if ($r.FailedCount -gt 0) { exit 1 }
