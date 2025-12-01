# Setup script for running replication backend on laptop
# This connects to the remote databases on the VMs

Write-Host "Setting up Replication Backend..." -ForegroundColor Green

# Check if Python is installed
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "Python not found. Please install Python 3.10 or higher." -ForegroundColor Red
    exit 1
}

# Check Python version
$pythonVersion = python --version
Write-Host "Found: $pythonVersion" -ForegroundColor Cyan

# Create virtual environment if it doesn't exist
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
} else {
    Write-Host "Virtual environment already exists" -ForegroundColor Cyan
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& .\.venv\Scripts\Activate.ps1

# Upgrade pip
Write-Host "Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip

# Install dependencies
Write-Host "Installing dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Test database connectivity:"
Write-Host "   python -c 'import asyncpg; print(\"asyncpg installed\")'" -ForegroundColor White
Write-Host ""
Write-Host "2. Run each node in separate terminals:" -ForegroundColor Cyan
Write-Host "   Terminal 1: .\run-node0.ps1" -ForegroundColor White
Write-Host "   Terminal 2: .\run-node1.ps1" -ForegroundColor White
Write-Host "   Terminal 3: .\run-node2.ps1" -ForegroundColor White
