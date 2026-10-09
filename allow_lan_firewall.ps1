# Run PowerShell as Administrator if Windows Firewall blocks the iPhone connection.
New-NetFirewallRule -DisplayName "JARVIS 8000 LAN" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
Write-Host "JARVIS LAN firewall rule created for Private networks." -ForegroundColor Green
