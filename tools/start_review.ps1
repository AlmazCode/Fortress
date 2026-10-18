param(
    [string]$TrainingRoot=(Join-Path $env:USERPROFILE 'FortressArtifacts\training-ready'),
    [string]$DataRoot=(Join-Path $env:LOCALAPPDATA 'Fortress\human-review-v1'),
    [int]$Port=8766,
    [switch]$NoBrowser
)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$python=Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Python environment is missing. Run tools/setup_local.ps1 first.' }
if (-not (Test-Path -LiteralPath (Join-Path $TrainingRoot 'prepared\readiness.json'))) { throw 'Existing prepared dataset was not found. Set -TrainingRoot.' }
$url="http://127.0.0.1:$Port/"
$listener=Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($listener) {
    $health=Invoke-RestMethod -Uri ($url+'healthz') -TimeoutSec 3
    $manifest=Get-Content -LiteralPath (Join-Path $DataRoot 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($health.app -ne 'fortress-human-review-v1' -or $health.manifest_sha256 -ne $manifest.sha256) { throw 'Port is used by another application or review dataset.' }
} else {
    New-Item -ItemType Directory -Force -Path $DataRoot | Out-Null
    $env:PYTHONDONTWRITEBYTECODE='1'
    $env:PYTHONIOENCODING='utf-8'
    $arguments=@('-B','-m','tools.label_review','--root',('"'+$TrainingRoot+'"'),'--data',('"'+$DataRoot+'"'),'--port',[string]$Port)
    $process=Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $DataRoot 'app.out.log') -RedirectStandardError (Join-Path $DataRoot 'app.err.log')
    $ready=$false
    for ($attempt=0; $attempt -lt 100; $attempt++) {
        $process.Refresh()
        if ($process.HasExited) { throw "Review app exited. Inspect $DataRoot\app.err.log" }
        try { $health=Invoke-RestMethod -Uri ($url+'healthz') -TimeoutSec 1; $ready=$health.app -eq 'fortress-human-review-v1' } catch {}
        if ($ready) { break }
        Start-Sleep -Milliseconds 300
    }
    if (-not $ready) { throw "Startup was not confirmed. Inspect $DataRoot\app.err.log" }
}
Write-Output "Annotation: $url"
Write-Output "Answers: $DataRoot\review.sqlite3"
if (-not $NoBrowser) { Start-Process $url }
