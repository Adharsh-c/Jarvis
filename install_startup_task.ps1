param([string]$ProjectRoot = $PSScriptRoot)
$TaskName = 'JARVIS V6 Voice Agent'
$Script = Join-Path $ProjectRoot 'run_voice_agent.ps1'
$Action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Script`""
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Description 'Starts JARVIS V6 desktop voice agent at Windows logon.' -Force
Write-Host "Installed: $TaskName"
