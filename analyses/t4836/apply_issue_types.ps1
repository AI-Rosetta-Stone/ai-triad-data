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
.PARAMETER ApprovedSha256
    Required with -Apply or -Rollback (SO condition C2, e/421#2): the LF-normalized sha256 of
    frozen_issue_types.json that was actually reviewed and approved. The script refuses to
    mutate anything if the file on disk doesn't hash to exactly this value -- so a frozen list
    that drifted after approval (edited, regenerated, or swapped) can't silently get applied.
    Not required for a dry run, which is non-mutating.
#>
param(
    [Parameter(Mandatory)][string]$TargetPath,
    [string]$ModulePath = 'C:\Users\jsnov\repos\ai-triad-research\scripts\AITriad\AITriad.psd1',
    [string]$ApprovedSha256,
    [switch]$Apply,
    [switch]$Rollback
)
$ErrorActionPreference = 'Stop'
Import-Module $ModulePath -Force -WarningAction SilentlyContinue

$FrozenPath = Join-Path $PSScriptRoot 'frozen_issue_types.json'
$FrozenRaw = [System.IO.File]::ReadAllText($FrozenPath, [System.Text.Encoding]::UTF8)

if ($Apply -or $Rollback) {
    # New-ActionableError isn't exported from AITriad (an internal Private helper) -- this is a
    # standalone orchestration script, not a module cmdlet, so a plain throw with a clear message
    # is the right fit here.
    if (-not $ApprovedSha256) {
        throw "-ApprovedSha256 is required for -Apply or -Rollback (SO condition C2, e/421#2). " +
              "Pass -ApprovedSha256 <hash> with the reviewed/approved frozen-file hash -- this script " +
              "prints the actual LF-normalized hash on refusal, for comparison against the approval."
    }
    # LF-normalize before hashing -- the approved hash is computed the same way, so a pure
    # line-ending difference (e.g. git's core.autocrlf) never causes a spurious refusal, but any
    # REAL content drift still does.
    $Normalized = $FrozenRaw -replace "`r`n", "`n"
    $Bytes = [System.Text.Encoding]::UTF8.GetBytes($Normalized)
    $ActualHash = [System.BitConverter]::ToString([System.Security.Cryptography.SHA256]::Create().ComputeHash($Bytes)).Replace('-', '').ToLowerInvariant()
    if ($ActualHash -ne $ApprovedSha256.ToLowerInvariant()) {
        throw "frozen_issue_types.json hashes to $ActualHash, not the approved $ApprovedSha256 -- " +
              "REFUSING to write anything. The frozen file has drifted since approval; do not proceed " +
              "without re-review. If this drift is expected (e.g. a legitimate re-freeze), get a new " +
              "approval and pass its new hash."
    }
    Write-Host "Approved-hash check passed: $ActualHash"
}

$Frozen = $FrozenRaw | ConvertFrom-Json
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
