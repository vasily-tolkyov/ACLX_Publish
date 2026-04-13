param(
    [string]$InstallRoot = ""
)

$ErrorActionPreference = "Stop"
$ResolvedRoot = if ($InstallRoot) { $InstallRoot } else { Join-Path $env:USERPROFILE ".aclx-hybrid-share\\current" }

if (Test-Path -LiteralPath $ResolvedRoot) {
    Remove-Item -LiteralPath $ResolvedRoot -Recurse -Force
}

$Parent = Split-Path -Parent $ResolvedRoot
if ($Parent -and (Test-Path -LiteralPath $Parent)) {
    $Remaining = Get-ChildItem -Force -LiteralPath $Parent
    if ($Remaining.Count -eq 0) {
        Remove-Item -LiteralPath $Parent -Force
    }
}
