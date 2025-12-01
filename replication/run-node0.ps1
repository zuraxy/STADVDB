# Run Node0 (Central Node) - connects to ccscloud.dlsu.edu.ph:60832

Write-Host "Starting Node0 (Central Node)..." -ForegroundColor Green
Write-Host "   Database: ccscloud.dlsu.edu.ph:60832/node0db" -ForegroundColor Cyan
Write-Host "   API Port: 8000" -ForegroundColor Cyan
Write-Host ""

# Activate virtual environment
& .\.venv\Scripts\Activate.ps1

# Copy node0 config
Copy-Item .env.node0 .env -Force

# Set PYTHONPATH to parent directory so relative imports work
$env:PYTHONPATH = (Get-Item .).Parent.FullName

# Run with uvicorn using module syntax (stay in replication dir so .env is found)
Write-Host "Starting server..." -ForegroundColor Yellow
python -m uvicorn replication.main:app --host 0.0.0.0 --port 8000 --reload
