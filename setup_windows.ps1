$ErrorActionPreference="Stop"
Set-Location "$PSScriptRoot\backend"
if (!(Test-Path .venv)) { py -3.12 -m venv .venv }
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item ..\.env.example .env }
Write-Host "Setup complete. Start Ollama and pull your local model first:" -ForegroundColor Green
Write-Host "ollama pull qwen2.5-coder:7b" -ForegroundColor Gray
Write-Host "Then configure backend\.env and run:" -ForegroundColor White
Write-Host "python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000" -ForegroundColor Gray
