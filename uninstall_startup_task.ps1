$TaskName = 'JARVIS V6 Voice Agent'
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "Removed: $TaskName"
