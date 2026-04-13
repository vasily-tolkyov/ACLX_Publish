param(
    [string]$InstallRoot = "",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CodexArgs
)

$ErrorActionPreference = "Stop"
$ResolvedRoot = if ($InstallRoot) { $InstallRoot } else { Join-Path $env:USERPROFILE ".aclx-hybrid-share\\current" }
$InstalledLauncher = Join-Path $ResolvedRoot "start_hybrid_codex.ps1"

if (-not (Test-Path -LiteralPath $InstalledLauncher)) {
    throw "Installed launcher not found at '$InstalledLauncher'. Run .\\install.ps1 first."
}

& $InstalledLauncher @CodexArgs
exit $LASTEXITCODE
