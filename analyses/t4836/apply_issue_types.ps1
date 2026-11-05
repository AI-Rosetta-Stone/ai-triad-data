#Requires -Version 7
<#
.SYNOPSIS
    t/4836: apply / dry-run / roll back the issue_types corpus write. The runner for the frozen
    list at analyses/t4836/frozen_issue_types.json, via the ai-triad-research cmdlet
    Set-IssueTypeTags (PR #4561).
.DESCRIPTION
    -Apply writes graph_attributes.issue_types + issue_types_provenance for the 1,311 accepted
    proposals in the frozen list. Without -Apply, runs a -WhatIf dry run (validates, writes
    nothing). -Rollback removes both keys from every frozen-list node id, restoring the
    pre-write state exactly (verified: `git diff` against the pre-apply commit is empty after
    rollback). Never re-derives the target list from issue-type-proposals.json -- always reads
    the frozen file, per /data-mutation discipline.
.PARAMETER TargetPath
    Directory holding the 4 taxonomy node files. Point this at a /data-mutation worktree, never
    the shared checkout directly.
.PARAMETER ModulePath
    Path to AITriad.psd1/psm1. Defaults to the sibling ai-triad-research checkout's module.
#>
param(
    [Parameter(Mandatory)][string]$TargetPath,
    [string]$ModulePath = 'C:\Users\jsnov\repos\ai-triad-research\scripts\AITriad\AITriad.psd1',
    [switch]$Apply,
    [switch]$Rollback
)
$ErrorActionPreference = 'Stop'
Import-Module $ModulePath -Force -WarningAction SilentlyContinue

$FrozenPath = Join-Path $PSScriptRoot 'frozen_issue_types.json'
$Frozen = [System.IO.File]::ReadAllText($FrozenPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
$entries = @($Frozen.entries)
Write-Host "Frozen entries: $($entries.Count)"

if ($Rollback) {
    Write-Host "=== ROLLBACK: removing graph_attributes.issue_types* from $($entries.Count) node(s) ==="
    $filesByPrefix = @{ acc = 'accelerationist.json'; saf = 'safetyist.json'; skp = 'skeptic.json'; sit = 'situations.json' }
    $groups = [ordered]@{}
    foreach ($e in $entries) {
        $prefix = ([regex]::Match($e.node_id, '^([a-z]+)-')).Groups[1].Value
        $file = $filesByPrefix[$prefix]
        $filePath = Join-Path $TargetPath $file
        if (-not $groups.Contains($filePath)) { $groups[$filePath] = [System.Collections.Generic.List[hashtable]]::new() }
        $groups[$filePath].Add(@{ NodeId = $e.node_id; Path = @('graph_attributes', 'issue_types'); Remove = $true })
        $groups[$filePath].Add(@{ NodeId = $e.node_id; Path = @('graph_attributes', 'issue_types_provenance'); Remove = $true })
    }
    $totalApplied = 0
    foreach ($filePath in $groups.Keys) {
        $result = Save-JsonNodeFieldEdits -Path $filePath -Edits $groups[$filePath].ToArray() -Confirm:$false
        Write-Host "$filePath -> Applied=$($result.Applied) NotFound=$($result.NotFound.Count)"
        $totalApplied += $result.Applied
    }
    Write-Host "=== ROLLBACK DONE: $totalApplied edit(s) applied ==="
    return
}

$Assignments = @($entries | ForEach-Object {
    # $_.provenance.confidence comes from ConvertFrom-Json as a PSCustomObject (no .Keys) --
    # Set-IssueTypeTags expects a real hashtable. Convert explicitly rather than passing it
    # through untouched.
    $confidenceHash = @{}
    if ($_.provenance.confidence) {
        foreach ($prop in $_.provenance.confidence.PSObject.Properties) { $confidenceHash[$prop.Name] = $prop.Value }
    }
    @{
        NodeId     = $_.node_id
        Types      = @($_.types)
        Provenance = @{
            Method        = $_.provenance.method
            Model         = $_.provenance.model
            PromptVersion = $_.provenance.prompt_version
            RunId         = $_.provenance.run_id
            ClassifiedAt  = $_.provenance.classified_at
            Confidence    = $confidenceHash
            Rationale     = $_.provenance.rationale
        }
    }
})

if ($Apply) {
    Write-Host "=== APPLYING $($Assignments.Count) assignment(s) ==="
    $Result = Set-IssueTypeTags -Assignment $Assignments -TargetPath $TargetPath -Confirm:$false
    $Result | Format-List *
    Write-Host "=== APPLY DONE ==="
} else {
    Write-Host "=== DRY RUN (-WhatIf) ==="
    Set-IssueTypeTags -Assignment $Assignments -TargetPath $TargetPath -WhatIf
    Write-Host "=== DRY RUN DONE (nothing written) ==="
}
