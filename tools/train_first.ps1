param(
    [string]$ArtifactsRoot = (Join-Path $env:USERPROFILE 'FortressArtifacts\training-v1'),
    [string]$RunName = ('run-' + (Get-Date -Format 'yyyyMMdd-HHmmss')),
    [string]$Resume,
    [int]$StopAfterEpochs = 0,
    [switch]$EvaluateHoldout
)
$ErrorActionPreference = 'Stop'
if ($EvaluateHoldout -and $StopAfterEpochs -gt 0) { throw 'Do not evaluate the holdout during a short setup smoke.' }
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$pythonPath = Join-Path (Get-Location).Path '.venv\Scripts\python.exe'
$launch = Get-Content -LiteralPath (Join-Path $ArtifactsRoot 'launch.json') -Raw | ConvertFrom-Json
if (-not $launch.videoTrainingReady) { throw 'Run setup_training.ps1 first.' }
if ($RunName -notmatch '^[a-zA-Z0-9][a-zA-Z0-9_-]{0,80}$') { throw 'Invalid RunName.' }
$runDirectory = Join-Path $ArtifactsRoot $RunName
if (Test-Path -LiteralPath $runDirectory) { throw 'Choose a new RunName; previous runs are preserved.' }
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:CUBLAS_WORKSPACE_CONFIG = ':4096:8'
$trainingArguments = @('-B', '-m', 'ml.cli', 'baseline', 'train', '--cache', $launch.cache,
                       '--config', $launch.config, '--output-dir', $runDirectory, '--allow-real-training')
if ($Resume) { $trainingArguments += @('--resume', $Resume) }
if ($StopAfterEpochs -gt 0) { $trainingArguments += @('--stop-after-epochs', [string]$StopAfterEpochs) }
& $pythonPath @trainingArguments
if ($LASTEXITCODE -ne 0) { throw 'Training failed; inspect failure.json and last.pt in the run directory.' }
if ($EvaluateHoldout) {
    & $pythonPath -B -m ml.cli baseline evaluate --cache $launch.cache --checkpoint (Join-Path $runDirectory 'best.pt') `
        --output (Join-Path $runDirectory 'internal_holdout.json') --device $launch.device
    if ($LASTEXITCODE -ne 0) { throw 'Holdout evaluation failed.' }
}
Write-Output "Run saved: $runDirectory"
