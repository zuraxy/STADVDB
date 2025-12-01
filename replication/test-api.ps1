# Run pytest tests for the replication system

Write-Host "Running Unit Tests..." -ForegroundColor Green
Write-Host ""

# Activate virtual environment
& .\.venv\Scripts\Activate.ps1

# Set PYTHONPATH so imports work
$env:PYTHONPATH = (Get-Item .).Parent.FullName

# Run pytest
Write-Host "Running pytest..." -ForegroundColor Cyan
pytest tests/ -v --tb=short

Write-Host ""
Write-Host "Test run complete!" -ForegroundColor Green
