param(
    [string]$Python = "python",
    [string]$SourceCodexHome = "",
    [string]$InstallRoot = ""
)

$ErrorActionPreference = "Stop"
$PackRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Tool = Join-Path $PackRoot "tools\\install_share_pack.py"

$Args = @($Tool, "--pack-root", $PackRoot, "--python", $Python)
if ($SourceCodexHome) {
    $Args += @("--source-home", $SourceCodexHome)
}
if ($InstallRoot) {
    $Args += @("--install-root", $InstallRoot)
}

& $Python @Args
exit $LASTEXITCODE
