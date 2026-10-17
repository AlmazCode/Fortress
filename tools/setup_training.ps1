param(
    [Parameter(Mandatory = $true)][string]$DatasetPackage,
    [string]$ArtifactsRoot = (Join-Path $env:USERPROFILE 'FortressArtifacts\training-v1'),
    [string]$UvPath = 'uv',
    [ValidateSet('cuda', 'cpu')][string]$Device = 'cuda',
    [ValidateSet('global', 'three_crop')][string]$Views = 'three_crop'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath (Join-Path $DatasetPackage 'annotations\video_labels.json'))) {
    throw 'DatasetPackage must be the extracted annotation package directory.'
}
New-Item -ItemType Directory -Force -Path $ArtifactsRoot | Out-Null
$extra = if ($Device -eq 'cuda') { 'ml-cuda' } else { 'ml' }
& $UvPath sync --locked --extra $extra --group test --no-build
if ($LASTEXITCODE -ne 0) { throw 'Locked environment installation failed.' }
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:CUBLAS_WORKSPACE_CONFIG = ':4096:8'
function Invoke-Baseline([string[]]$Arguments) {
    & $pythonPath -B -m ml.cli baseline @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Training setup failed at $($Arguments[0])." }
}
Invoke-Baseline -Arguments @('preflight', '--device', $Device)
$weightsDirectory = Join-Path $ArtifactsRoot 'weights'
Invoke-Baseline -Arguments @('weights', '--output-dir', $weightsDirectory)
$receipt = Get-Content -LiteralPath (Join-Path $weightsDirectory 'weights_receipt.json') -Raw | ConvertFrom-Json
$preparedDirectory = Join-Path $ArtifactsRoot 'prepared'
Invoke-Baseline -Arguments @('prepare', '--package', $DatasetPackage, '--output-dir', $preparedDirectory, '--allow-dataset-use')
$cacheDirectory = Join-Path $ArtifactsRoot ('cache-' + $Views)
Invoke-Baseline -Arguments @('cache', '--prepared', $preparedDirectory, '--output-dir', $cacheDirectory,
                 '--encoder-weights', $receipt.path, '--encoder-sha256', $receipt.sha256, '--device', $Device, '--views', $Views)
$config = Get-Content -LiteralPath (Join-Path $projectRoot 'ml\config\video_baseline.json') -Raw | ConvertFrom-Json
$config.device = $Device
$config | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $ArtifactsRoot 'train_config.json') -Encoding utf8
$ready = @{
    projectRoot = $projectRoot; datasetPackage = (Resolve-Path -LiteralPath $DatasetPackage).Path
    cache = $cacheDirectory; config = (Join-Path $ArtifactsRoot 'train_config.json')
    device = $Device; videoTrainingReady = $true; productionReady = $false
    accuracyTarget = 0.8; accuracyMeasured = $false
}
$ready | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $ArtifactsRoot 'launch.json') -Encoding utf8
$starter = "@echo off`r`nchcp 65001 >nul`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $projectRoot 'tools\train_first.ps1')`" -ArtifactsRoot `"$ArtifactsRoot`" %*`r`npause`r`n"
[System.IO.File]::WriteAllText((Join-Path $ArtifactsRoot 'START_TRAINING.cmd'), $starter, [System.Text.UTF8Encoding]::new($false))
Write-Output "Ready. Start tools\train_first.ps1 -ArtifactsRoot `"$ArtifactsRoot`". Test evaluation is a separate optional step."
