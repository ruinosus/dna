#!/usr/bin/env pwsh
param([switch]$Json, [Parameter(ValueFromRemainingArguments = $true)][string[]]$FeatureDescription)

$repoRoot = git rev-parse --show-toplevel 2>$null
if (-not $repoRoot) { $repoRoot = (Get-Location).Path }
$desc = ($FeatureDescription -join ' ').ToLower()
$shortName = ($desc -replace '[^a-z0-9]+', '-').Trim('-').Substring(0, [Math]::Min(40, $desc.Length))
$next = '{0:D3}' -f ((Get-ChildItem "$repoRoot/specs" -ErrorAction SilentlyContinue).Count + 1)
$branch = "$next-$shortName"
$specDir = "$repoRoot/specs/$branch"
New-Item -ItemType Directory -Force -Path $specDir | Out-Null
Copy-Item "$repoRoot/.specify/templates/spec-template.md" "$specDir/spec.md"
[pscustomobject]@{ BRANCH_NAME = $branch; SPEC_FILE = "$specDir/spec.md" } | ConvertTo-Json -Compress
