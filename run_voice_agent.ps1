$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VoiceDir = Join-Path $Root 'voice-agent'
$Py = Join-Path $VoiceDir '.venv\Scripts\python.exe'
if (-not (Test-Path $Py)) { $Py = 'python' }
$EnvFile = Join-Path $VoiceDir '.env'
if (-not (Test-Path $EnvFile)) { Write-Host 'Create voice-agent\.env from voice-agent\.env.example first.'; exit 1 }
Set-Location $VoiceDir
& $Py '.\voice_agent.py'
