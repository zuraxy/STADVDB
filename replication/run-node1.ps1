# Run Node1 (Partition 1) - connects to ccscloud.dlsu.edu.ph:60833

Write-Host "Starting Node1 (Partition 1)..." -ForegroundColor Green
Write-Host "   Database: ccscloud.dlsu.edu.ph:60833/node1db" -ForegroundColor Cyan
Write-Host "   API Port: 8001" -ForegroundColor Cyan
Write-Host ""

# Navigate to replication directory first
Set-Location $PSScriptRoot

# Activate virtual environment
& .\.venv\Scripts\Activate.ps1

# Copy node1 config
Copy-Item .env.node1 .env -Force

# Set PYTHONPATH to parent directory so relative imports work
$env:PYTHONPATH = (Get-Item .).Parent.FullName

# Run with uvicorn using module syntax (stay in replication dir so .env is found)
Write-Host "Starting server..." -ForegroundColor Yellow
python -m uvicorn replication.main:app --host 0.0.0.0 --port 8001 --reload
