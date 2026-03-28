# Intellifox — run API locally (Windows PowerShell)
# From project folder:  .\run_local.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .env)) {
    if (Test-Path .env.example) {
        Copy-Item .env.example .env
        Write-Host "Created .env from .env.example — edit .env and set GEMINI_API_KEY before using Gemini features." -ForegroundColor Yellow
    }
}

if (-not (Test-Path .venv\Scripts\Activate.ps1)) {
    Write-Host "No .venv found. Run:  python -m venv .venv" -ForegroundColor Yellow
    Write-Host "Then:  .\.venv\Scripts\Activate.ps1  &&  pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

& .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -q

if (-not (Test-Path banking_knowledge.json)) {
    Write-Host "Generating banking_knowledge.json ..." -ForegroundColor Cyan
    python build_banking_knowledge.py
}

$env:UVICORN_RELOAD = if ($env:UVICORN_RELOAD) { $env:UVICORN_RELOAD } else { "1" }
$env:UVICORN_HOST = if ($env:UVICORN_HOST) { $env:UVICORN_HOST } else { "127.0.0.1" }

$port = if ($env:PORT) { $env:PORT } else { "8080" }
Write-Host "Starting http://$($env:UVICORN_HOST):$port  (reload=$env:UVICORN_RELOAD)" -ForegroundColor Green
python main.py
