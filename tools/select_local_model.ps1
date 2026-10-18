param(
    [Parameter(Mandatory=$true)][string]$ModelBundle,
    [string]$PrivateRoot=(Join-Path $env:LOCALAPPDATA 'Fortress')
)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$python=Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run tools/setup_local.ps1 first.' }
$env:PYTHONIOENCODING='utf-8'
& $python -B -m backend.local.select_model --config (Join-Path $PrivateRoot 'local-config.json') --bundle $ModelBundle
if ($LASTEXITCODE -ne 0) { throw 'Model selection failed; the previous configuration is preserved.' }
