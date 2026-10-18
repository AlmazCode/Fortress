param([string]$PrivateRoot=(Join-Path $env:LOCALAPPDATA 'Fortress'), [switch]$Background)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$python=Join-Path $projectRoot '.venv\Scripts\python.exe'
$configPath=Join-Path $PrivateRoot 'local-config.json'
if (-not (Test-Path -LiteralPath $configPath) -or -not (Test-Path -LiteralPath $python)) { throw 'Run tools/setup_local.ps1 first.' }
$config=Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$listener=Get-NetTCPConnection -State Listen -LocalPort $config.port -ErrorAction SilentlyContinue
if ($listener) { throw 'Configured port is already in use. Check the existing service before starting another.' }
Set-Location -LiteralPath $projectRoot
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONIOENCODING='utf-8'
$arguments=@('-B','-m','backend.local.app','--config',('"'+$configPath+'"'),'--port',[string]$config.port)
if ($Background) {
    $logDirectory=Join-Path $PrivateRoot 'logs'
    New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
    $process=Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDirectory 'service.out.log') -RedirectStandardError (Join-Path $logDirectory 'service.err.log')
    $ready=$false
    for ($i=0; $i -lt 100; $i++) {
        if ($process.HasExited) { throw "Service exited. Inspect $logDirectory" }
        try { $health=Invoke-RestMethod -Uri "http://127.0.0.1:$($config.port)/healthz" -TimeoutSec 1; $ready=$health.mode -eq 'prototype' } catch {}
        if ($ready) { break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw 'Startup was not confirmed. Inspect private logs.' }
    Write-Output "Web interface: http://127.0.0.1:$($config.port)/"
    Write-Output "API base: http://127.0.0.1:$($config.port)/api/v1"
    Write-Output "Private API key: $(Join-Path $PrivateRoot 'jury-access.json')"
} else {
    & $python -B -m backend.local.app --config $configPath --port $config.port
    if ($LASTEXITCODE -ne 0) { throw 'Service failed. Inspect the error above.' }
}
