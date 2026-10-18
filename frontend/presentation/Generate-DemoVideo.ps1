param(
  [Parameter(Mandatory = $true)][string]$FfmpegPath,
  [Parameter(Mandatory = $true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$executable = (Resolve-Path -LiteralPath $FfmpegPath).Path
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$outputRoot = (Resolve-Path -LiteralPath $OutputDirectory).Path
$sourceImage = Join-Path $PSScriptRoot 'synthetic-bank-lobby.png'
foreach ($sample in @(@('demo-lobby-01.mp4', 8), @('demo-lobby-02.mp4', 12))) {
  $destination = Join-Path $outputRoot $sample[0]
  if (Test-Path -LiteralPath $destination) { throw "Output already exists: $destination" }
  & $executable -hide_banner -loglevel error -loop 1 -framerate 24 -i $sourceImage -t $sample[1] -vf 'scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720' -an -c:v libx264 -preset fast -pix_fmt yuv420p -movflags +faststart $destination
  if ($LASTEXITCODE -ne 0) { throw 'FFmpeg could not create the presentation clip.' }
}
