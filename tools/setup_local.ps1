param(
    [string]$PrivateRoot = (Join-Path $env:LOCALAPPDATA 'Fortress'),
    [string]$ModelBundle = (Join-Path $env:USERPROFILE 'FortressArtifacts\training-ready\transition-state-bundle-v1'),
    [ValidateSet('cuda','cpu')][string]$Device = 'cuda',
    [ValidateRange(1024,65535)][int]$Port = 8000,
    [switch]$SkipInstall
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$PrivateRoot = [IO.Path]::GetFullPath($PrivateRoot)
if ($PrivateRoot.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or $PrivateRoot -eq $projectRoot) { throw 'PrivateRoot must be outside the checkout.' }
New-Item -ItemType Directory -Force -Path $PrivateRoot | Out-Null
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe $PrivateRoot /inheritance:r /grant:r "*${sid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Cannot restrict private directory permissions.' }
$taskTools = Join-Path $PrivateRoot 'tools'
New-Item -ItemType Directory -Force -Path $taskTools | Out-Null
$uvPath = Join-Path $taskTools 'uv\uv.exe'
if (-not (Test-Path -LiteralPath $uvPath)) {
    $metadata = Invoke-RestMethod -Uri 'https://pypi.org/pypi/uv/0.13.1/json'
    $wheel = @($metadata.urls | Where-Object { $_.filename -eq 'uv-0.13.1-py3-none-win_amd64.whl' })
    if ($wheel.Count -ne 1) { throw 'Expected uv Windows wheel not found.' }
    $archive = Join-Path $taskTools 'uv.whl'
    Invoke-WebRequest -Uri $wheel[0].url -OutFile $archive -UseBasicParsing
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash -ne $wheel[0].digests.sha256) { throw 'uv wheel SHA mismatch.' }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $unpack = Join-Path $taskTools 'uv-wheel'
    if (-not (Test-Path -LiteralPath $unpack)) { [IO.Compression.ZipFile]::ExtractToDirectory($archive, $unpack) }
    $binary = @(Get-ChildItem -LiteralPath $unpack -Filter uv.exe -Recurse)
    if ($binary.Count -ne 1) { throw 'Expected one uv executable.' }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $uvPath) | Out-Null
    Copy-Item -LiteralPath $binary[0].FullName -Destination $uvPath
}
$ffmpegDir = Join-Path $taskTools 'ffmpeg\ffmpeg-9.0.2-essentials_build\bin'
if (-not (Test-Path -LiteralPath (Join-Path $ffmpegDir 'ffprobe.exe'))) {
    $archive = Join-Path $taskTools 'ffmpeg-release-essentials.zip'
    if (-not (Test-Path -LiteralPath $archive)) {
        Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip' -OutFile $archive -UseBasicParsing
    }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash -ne '60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba') { throw 'FFmpeg archive SHA mismatch.' }
    Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $taskTools 'ffmpeg')
}
Set-Location -LiteralPath $projectRoot
if (-not $SkipInstall) {
    $extra = if ($Device -eq 'cuda') { 'ml-cuda' } else { 'ml' }
    & $uvPath sync --locked --extra $extra --group test --python 3.11
    if ($LASTEXITCODE -ne 0) { throw 'Locked Python setup failed.' }
    Push-Location (Join-Path $projectRoot 'frontend')
    try {
        & npm.cmd ci --ignore-scripts --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } finally { Pop-Location }
}
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Missing Python environment. Run setup without -SkipInstall.' }
$env:PATH = $ffmpegDir + [IO.Path]::PathSeparator + $env:PATH
& $python -B -c "import av,fastapi,uvicorn,torch,torchvision; assert '$Device' != 'cuda' or torch.cuda.is_available(); print('Python/ML runtime available')"
if ($LASTEXITCODE -ne 0) { throw 'Python/ML preflight failed.' }
if (-not (Test-Path -LiteralPath (Join-Path $ModelBundle 'bundle.json'))) { throw 'Copy the private trained model bundle to ModelBundle first; weights are not in Git.' }
$bundleRoot = Join-Path $PrivateRoot 'models\control-v1'
New-Item -ItemType Directory -Force -Path $bundleRoot | Out-Null
$expected = 'c5c673f54cabb1e675f058950454a4f431d39aae5fa656c26cc79f7853b0a077'
if ((Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $ModelBundle 'weights.pt')).Hash -ne $expected) { throw 'Expected the measured GRU control bundle; weight SHA mismatch.' }
foreach ($file in @('bundle.json','weights.pt')) {
    $source = Join-Path $ModelBundle $file
    $target = Join-Path $bundleRoot $file
    if ([IO.Path]::GetFullPath($source) -ne [IO.Path]::GetFullPath($target)) { Copy-Item -LiteralPath $source -Destination $target -Force }
}
$accessPath = Join-Path $PrivateRoot 'jury-access.json'
if (Test-Path -LiteralPath $accessPath) {
    $access = Get-Content -LiteralPath $accessPath -Raw | ConvertFrom-Json
    $apiKey = $access.api_key
    if (-not $apiKey -or $apiKey.Length -lt 32) { throw 'Existing private key is invalid; inspect it before replacing.' }
} else {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $apiKey = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
}
$utf8 = [Text.UTF8Encoding]::new($false)
$access = @{ web_interface_url="http://127.0.0.1:$Port/"; api_base_url="http://127.0.0.1:$Port/api/v1"; api_key=$apiKey; scope='local prototype; external access not configured' }
[IO.File]::WriteAllText($accessPath, ($access | ConvertTo-Json), $utf8)
$config = @{ runtime_root=(Join-Path $PrivateRoot 'runtime'); bundle_root=$bundleRoot; api_key_file=$accessPath; ffmpeg_dir=$ffmpegDir; device=$Device; port=$Port; prototype_enabled=$true }
[IO.File]::WriteAllText((Join-Path $PrivateRoot 'local-config.json'), ($config | ConvertTo-Json), $utf8)
Write-Output "Setup complete. Private access details: $accessPath"
Write-Output 'Start: powershell -ExecutionPolicy Bypass -File tools/start_local.ps1'
Write-Output 'Prototype only: measured accuracy 71.30%; event/rule validation remains incomplete.'
