$ErrorActionPreference="Stop"
$r = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method Get
$r | ConvertTo-Json -Depth 8
if ($r.status -ne "ok") { exit 1 }
