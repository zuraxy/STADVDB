# Check if databases exist
# Usage: .\check-setup.ps1

Write-Host "`n=== Checking Setup Status ===" -ForegroundColor Cyan

# Check PostgreSQL
Write-Host "`n1. PostgreSQL Installation:" -ForegroundColor Yellow
$pgVersion = psql --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ $pgVersion" -ForegroundColor Green
} else {
    Write-Host "  ✗ PostgreSQL not found" -ForegroundColor Red
    Write-Host "    Install from: https://www.postgresql.org/download/windows/" -ForegroundColor Gray
}

# Check PostgreSQL service
Write-Host "`n2. PostgreSQL Service:" -ForegroundColor Yellow
$pgService = Get-Service postgresql* -ErrorAction SilentlyContinue
if ($pgService) {
    Write-Host "  ✓ Service: $($pgService.DisplayName) - Status: $($pgService.Status)" -ForegroundColor Green
} else {
    Write-Host "  ✗ PostgreSQL service not found" -ForegroundColor Red
}

# Check Python
Write-Host "`n3. Python Installation:" -ForegroundColor Yellow
$pyVersion = python --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ $pyVersion" -ForegroundColor Green
} else {
    Write-Host "  ✗ Python not found" -ForegroundColor Red
}

# Check Node.js
Write-Host "`n4. Node.js Installation:" -ForegroundColor Yellow
$nodeVersion = node --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ Node.js $nodeVersion" -ForegroundColor Green
} else {
    Write-Host "  ✗ Node.js not found" -ForegroundColor Red
}

# Check Python venv
Write-Host "`n5. Python Virtual Environment:" -ForegroundColor Yellow
if (Test-Path ".\replication\.venv") {
    Write-Host "  ✓ Virtual environment exists" -ForegroundColor Green
} else {
    Write-Host "  ✗ Virtual environment not created" -ForegroundColor Red
    Write-Host "    Run: cd replication; python -m venv .venv" -ForegroundColor Gray
}

# Check frontend node_modules
Write-Host "`n6. Frontend Dependencies:" -ForegroundColor Yellow
if (Test-Path ".\frontend\web-app\node_modules") {
    Write-Host "  ✓ Node modules installed" -ForegroundColor Green
} else {
    Write-Host "  ✗ Node modules not installed" -ForegroundColor Red
    Write-Host "    Run: cd frontend\web-app; npm install" -ForegroundColor Gray
}

Write-Host "`n=== Next Steps ===" -ForegroundColor Cyan
Write-Host "1. Create databases (if needed):" -ForegroundColor Yellow
Write-Host "   psql -U postgres" -ForegroundColor Gray
Write-Host "   Then run: CREATE DATABASE node0db; CREATE DATABASE node1db; CREATE DATABASE node2db;" -ForegroundColor Gray
Write-Host "`n2. Setup Python environment (if not done):" -ForegroundColor Yellow
Write-Host "   cd replication" -ForegroundColor Gray
Write-Host "   python -m venv .venv" -ForegroundColor Gray
Write-Host "   .\.venv\Scripts\Activate.ps1" -ForegroundColor Gray
Write-Host "   pip install -r requirements.txt" -ForegroundColor Gray
Write-Host "`n3. Initialize databases:" -ForegroundColor Yellow
Write-Host "   cd replication" -ForegroundColor Gray
Write-Host "   .\.venv\Scripts\Activate.ps1" -ForegroundColor Gray
Write-Host "   python init_db.py" -ForegroundColor Gray
Write-Host "`n4. Start the system:" -ForegroundColor Yellow
Write-Host "   .\start-nodes.ps1" -ForegroundColor Gray
Write-Host "   .\start-frontend.ps1" -ForegroundColor Gray
Write-Host ""
