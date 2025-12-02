# Complete setup script - Run this ONCE to set everything up
# Usage: .\setup.ps1

Write-Host "`n================================================================" -ForegroundColor Cyan
Write-Host "    STADVDB MCO2 - Distributed Database Setup" -ForegroundColor Cyan
Write-Host "================================================================`n" -ForegroundColor Cyan

# Get PostgreSQL password
$PG_PASSWORD = Read-Host "Enter your PostgreSQL password (for user 'postgres')" -AsSecureString
$BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($PG_PASSWORD)
$PG_PASSWORD_TEXT = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)

if (-not $PG_PASSWORD_TEXT) {
    Write-Host "❌ Password is required!" -ForegroundColor Red
    exit 1
}

# Step 1: Create databases
Write-Host "`n[1/4] Creating PostgreSQL databases..." -ForegroundColor Yellow
Write-Host "      Creating node0db, node1db, node2db" -ForegroundColor Gray

$env:PGPASSWORD = $PG_PASSWORD_TEXT

# Check if databases already exist
$existingDBs = psql -U postgres -t -c "SELECT datname FROM pg_database WHERE datname LIKE 'node%db';" 2>&1

if ($existingDBs -match "node0db") {
    Write-Host "      ⚠ Databases already exist. Skipping creation." -ForegroundColor Yellow
} else {
    psql -U postgres -c "CREATE DATABASE node0db;" 2>&1 | Out-Null
    psql -U postgres -c "CREATE DATABASE node1db;" 2>&1 | Out-Null
    psql -U postgres -c "CREATE DATABASE node2db;" 2>&1 | Out-Null
    Write-Host "      ✓ Databases created successfully" -ForegroundColor Green
}

# Step 2: Initialize database schema
Write-Host "`n[2/4] Initializing database schema..." -ForegroundColor Yellow
Write-Host "      Creating tables: orders, op_log, log_acknowledgements" -ForegroundColor Gray
Write-Host "      Applying partition constraints" -ForegroundColor Gray

cd replication
.\.venv\Scripts\python.exe init_db.py $PG_PASSWORD_TEXT
if ($LASTEXITCODE -eq 0) {
    Write-Host "      ✓ Schema initialized successfully" -ForegroundColor Green
} else {
    Write-Host "      ❌ Schema initialization failed" -ForegroundColor Red
}
cd ..

# Step 3: Setup frontend
Write-Host "`n[3/4] Setting up frontend..." -ForegroundColor Yellow

cd frontend\web-app

if (Test-Path "node_modules") {
    Write-Host "      ✓ Frontend dependencies already installed" -ForegroundColor Green
} else {
    Write-Host "      Installing npm packages..." -ForegroundColor Gray
    npm install 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "      ✓ Frontend dependencies installed" -ForegroundColor Green
    } else {
        Write-Host "      ❌ Frontend installation failed" -ForegroundColor Red
    }
}

# Create .env file
if (-not (Test-Path ".env")) {
    Write-Host "      Creating frontend .env file..." -ForegroundColor Gray
    "VITE_API_URL=http://localhost:8000" | Out-File -FilePath ".env" -Encoding utf8
    Write-Host "      ✓ Frontend .env created" -ForegroundColor Green
}

cd ..\..

# Step 4: Cleanup
Remove-Item Env:\PGPASSWORD

# Success message
Write-Host "`n================================================================" -ForegroundColor Green
Write-Host "    ✅ SETUP COMPLETE!" -ForegroundColor Green
Write-Host "================================================================`n" -ForegroundColor Green

Write-Host "Your distributed database system is ready!" -ForegroundColor White
Write-Host "`nTo start the system:" -ForegroundColor Yellow
Write-Host "  1. Open a new terminal and run: " -NoNewline
Write-Host ".\start-nodes.ps1" -ForegroundColor Cyan
Write-Host "     (This will start all 3 backend nodes)" -ForegroundColor Gray
Write-Host "`n  2. Open another terminal and run: " -NoNewline
Write-Host ".\start-frontend.ps1" -ForegroundColor Cyan
Write-Host "     (This will start the React frontend)" -ForegroundColor Gray
Write-Host "`n  3. Open your browser to: " -NoNewline
Write-Host "http://localhost:5173" -ForegroundColor Cyan

Write-Host "`nAPI Documentation available at:" -ForegroundColor Yellow
Write-Host "  • Node 0: http://localhost:8000/docs" -ForegroundColor Gray
Write-Host "  • Node 1: http://localhost:8001/docs" -ForegroundColor Gray
Write-Host "  • Node 2: http://localhost:8002/docs" -ForegroundColor Gray

Write-Host "`n================================================================`n" -ForegroundColor Cyan
