param(
    [string]$Python = "python",
    [string]$InstallRoot = ""
)

$ErrorActionPreference = "Stop"
$PackRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Tool = Join-Path $PackRoot "tools\\verify_share_pack.py"

$Args = @($Tool, "--pack-root", $PackRoot, "--python", $Python)
if ($InstallRoot) {
    $Args += @("--install-root", $InstallRoot)
}

& $Python @Args
exit $LASTEXITCODE
