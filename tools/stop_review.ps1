param([int]$Port=8766)
$ErrorActionPreference='Stop'
$url="http://127.0.0.1:$Port"
Invoke-WebRequest -Uri ($url+'/') -SessionVariable reviewSession -UseBasicParsing | Out-Null
Invoke-RestMethod -Method Post -Uri ($url+'/api/shutdown') -WebSession $reviewSession -Headers @{Origin=$url} -ContentType 'application/json' -Body '{}' | Out-Null
Write-Output 'Review app stopped. Answers remain saved on disk.'
