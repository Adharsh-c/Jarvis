$ErrorActionPreference = 'Stop'
Set-Location "$PSScriptRoot\backend"
if (-not (Test-Path .venv)) { py -3.12 -m venv .venv }
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Write-Host "Starting JARVIS on the local network..." -ForegroundColor Cyan
Write-Host "After startup, open http://<THIS-PC-IP>:8000/ on your iPhone." -ForegroundColor Yellow
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
