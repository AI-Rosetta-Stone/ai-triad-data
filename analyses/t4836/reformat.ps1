# t/4836 format-only fix: re-save the 4 taxonomy files touched by 902c800b through the canonical
# writer (Write-PovTaxonomyFile), to repair the compact-JSON insertion bug CI caught
# (Write-PovTaxonomyFile.Tests.ps1:100, byte-identical round trip).
$ModulePath = Join-Path $env:USERPROFILE 'repos\ai-triad-research\scripts\AITriad\AITriad.psm1'
Import-Module $ModulePath -Force -WarningAction SilentlyContinue -ErrorAction Stop
$Mod = Get-Module AITriad

$Files = @(
    'taxonomy/Origin/accelerationist.json',
    'taxonomy/Origin/safetyist.json',
    'taxonomy/Origin/skeptic.json',
    'taxonomy/Origin/situations.json'
)

foreach ($f in $Files) {
    $full = Join-Path (Get-Location) $f
    Write-Host "Reformatting $f ..."
    $data = & $Mod { param($p) Read-PovTaxonomyFile -Path $p } $full
    & $Mod { param($p, $d) Write-PovTaxonomyFile -Path $p -Data $d -AllowDirty } $full $data
    Write-Host "  done: $((Get-Item $full).Length) bytes"
}
