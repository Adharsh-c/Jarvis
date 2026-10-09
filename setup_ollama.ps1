Write-Host "JARVIS V9 Ollama setup" -ForegroundColor Cyan
Write-Host "This release uses local Ollama only. No cloud AI API key is required." -ForegroundColor Yellow

$backend = Join-Path $PSScriptRoot "backend"
$envFile = Join-Path $backend ".env"
$example = Join-Path $PSScriptRoot ".env.example"

if (-not (Test-Path $envFile)) {
    Copy-Item $example $envFile
    Write-Host "Created backend/.env from .env.example" -ForegroundColor Green
}

Write-Host "Install/start Ollama, then pull a local model:" -ForegroundColor White
Write-Host "  ollama pull qwen2.5-coder:7b" -ForegroundColor Gray
Write-Host "  ollama list" -ForegroundColor Gray
Write-Host ""
Write-Host "Then test JARVIS:" -ForegroundColor White
Write-Host "  cd backend" -ForegroundColor Gray
Write-Host "  .\.venv\Scripts\Activate.ps1" -ForegroundColor Gray
Write-Host "  python test_ai_providers.py" -ForegroundColor Gray
