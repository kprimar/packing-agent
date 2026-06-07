# Windows setup script for packing-agent
# Run once from the project root: .\setup.ps1

Write-Host "=== Packing Agent Setup ===" -ForegroundColor Cyan

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
} else {
    Write-Host "Virtual environment already exists." -ForegroundColor Green
}

Write-Host "Installing dependencies..." -ForegroundColor Yellow
.\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
.\.venv\Scripts\pip.exe install -r requirements.txt --quiet

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Activate the venv: .\.venv\Scripts\Activate.ps1"
Write-Host "  2. Set your API key:  `$env:ANTHROPIC_API_KEY = 'sk-...'"
Write-Host "  3. Run the agent:     python main.py"
