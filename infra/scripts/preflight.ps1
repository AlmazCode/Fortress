[CmdletBinding()]
param(
    [string]$OutputPath,
    [switch]$Strict,
    [ValidateRange(1,60)][int]$TimeoutSeconds = 8,
    [string]$ExternalUrl,
    [switch]$ProbeExternal,
    [string]$WanIp,
    [string]$PublicIp,
    [switch]$NetworkOnly,
    [switch]$ContainerSmoke,
    [string]$GpuImage
)
$ErrorActionPreference = 'Stop'
$recorderCommand = $null
foreach ($candidate in @('python', 'python3')) {
    $resolved = Get-Command $candidate -CommandType Application -ErrorAction SilentlyContinue | Where-Object { $_.Source -notlike '*WindowsApps*' } | Select-Object -First 1
    if ($resolved) { $recorderCommand = $resolved.Source; break }
}
if (-not $recorderCommand) {
    $fallback = [ordered]@{schema_version=1;report_status='bootstrap_blocked';readiness=@{service_ready=$false;gpu_ready=$false;external_access_verified=$false};blockers=@('No Python recorder found; install Python 3.11 before collecting the full report.');checks=@{}} | ConvertTo-Json -Depth 6
    if ($OutputPath) { $fallback | Set-Content -LiteralPath $OutputPath -Encoding utf8 }
    Write-Output $fallback
    exit 2
}
$sharedSource = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'preflight.sh') -Raw
$beginMarker = '# BEGIN_FORTRESS_PREFLIGHT_PY'
$endMarker = '# END_FORTRESS_PREFLIGHT_PY'
$beginPosition = $sharedSource.IndexOf($beginMarker)
$endPosition = $sharedSource.LastIndexOf($endMarker)
if ($beginPosition -lt 0 -or $endPosition -le $beginPosition) { throw 'Shared preflight recorder is missing or malformed' }
$pythonSource = $sharedSource.Substring($beginPosition + $beginMarker.Length, $endPosition - $beginPosition - $beginMarker.Length)
$probeArgs = @('--timeout', [string]$TimeoutSeconds)
if ($OutputPath) { $probeArgs += @('--output', $OutputPath) }
if ($Strict) { $probeArgs += '--strict' }
if ($ExternalUrl) { $probeArgs += @('--external-url', $ExternalUrl) }
if ($ProbeExternal) { $probeArgs += '--probe-external' }
if ($WanIp) { $probeArgs += @('--wan-ip', $WanIp) }
if ($PublicIp) { $probeArgs += @('--public-ip', $PublicIp) }
if ($NetworkOnly) { $probeArgs += '--network-only' }
if ($ContainerSmoke) { $probeArgs += '--container-smoke' }
if ($GpuImage) { $probeArgs += @('--gpu-image', $GpuImage) }
& $recorderCommand -c $pythonSource @probeArgs
exit $LASTEXITCODE
