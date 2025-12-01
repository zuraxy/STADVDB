# Run Node2 (Partition 2) - connects to ccscloud.dlsu.edu.ph:60834

Write-Host "Starting Node2 (Partition 2)..." -ForegroundColor Green
Write-Host "   Database: ccscloud.dlsu.edu.ph:60834/node2db" -ForegroundColor Cyan
Write-Host "   API Port: 8002" -ForegroundColor Cyan
Write-Host ""

# Navigate to replication directory first
Set-Location $PSScriptRoot

# Activate virtual environment
& .\.venv\Scripts\Activate.ps1

# Copy node2 config
Copy-Item .env.node2 .env -Force

# Set PYTHONPATH to parent directory so relative imports work
$env:PYTHONPATH = (Get-Item .).Parent.FullName

# Run with uvicorn using module syntax (stay in replication dir so .env is found)
Write-Host "Starting server..." -ForegroundColor Yellow
python -m uvicorn replication.main:app --host 0.0.0.0 --port 8002 --reload
