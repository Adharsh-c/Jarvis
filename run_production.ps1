$ErrorActionPreference="Stop"
Set-Location "$PSScriptRoot\backend"
if (!(Test-Path .venv)) { py -3.12 -m venv .venv }
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if (!(Test-Path .env)) { throw "backend\.env is missing. Copy .env.example to backend\.env and configure production secrets first." }
$env:JARVIS_ENV="production"
Write-Host "Starting JARVIS in production mode on 0.0.0.0:8000" -ForegroundColor Green
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
