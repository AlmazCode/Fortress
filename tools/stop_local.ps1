param([string]$PrivateRoot=(Join-Path $env:LOCALAPPDATA 'Fortress'))
$ErrorActionPreference='Stop'
$config=Get-Content -LiteralPath (Join-Path $PrivateRoot 'local-config.json') -Raw | ConvertFrom-Json
$access=Get-Content -LiteralPath $config.api_key_file -Raw | ConvertFrom-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$($config.port)/api/local/v1/shutdown" -Headers @{'X-API-Key'=$access.api_key} | Out-Null
Write-Output 'Graceful shutdown requested; active inference is cancelled and queued jobs remain on disk.'
