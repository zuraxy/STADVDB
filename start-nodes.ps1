# PowerShell script to start all 3 backend nodes
# Usage: .\start-nodes.ps1

Write-Host "=== Starting Distributed Database Nodes ===" -ForegroundColor Cyan
Write-Host ""

# Check if PostgreSQL password is set
$PG_PASSWORD = Read-Host "Enter your PostgreSQL password" -AsSecureString
$PG_PASSWORD_TEXT = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($PG_PASSWORD))

if (-not $PG_PASSWORD_TEXT) {
    Write-Host "Error: PostgreSQL password is required!" -ForegroundColor Red
    exit 1
}

# Check if venv exists
if (-not (Test-Path ".\replication\.venv")) {
    Write-Host "Virtual environment not found. Creating..." -ForegroundColor Yellow
    cd replication
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    cd ..
}

Write-Host "Starting Node 0 (Central - Port 8000)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", @"
cd '$PWD\replication';
.\.venv\Scripts\Activate.ps1;
`$env:DATABASE_DSN='postgresql://postgres:$PG_PASSWORD_TEXT@localhost:5432/node0db';
`$env:NODE_NAME='node0';
`$env:DEFAULT_MASTER='node0';
`$env:DEFAULT_MASTER_URL='http://localhost:8000';
`$env:PEER_NODES='[{\"name\":\"node0\",\"url\":\"http://localhost:8000\"},{\"name\":\"node1\",\"url\":\"http://localhost:8001\"},{\"name\":\"node2\",\"url\":\"http://localhost:8002\"}]';
`$env:POLL_INTERVAL='5';
`$env:APPLIER_INTERVAL='2';
`$env:PROMOTED='false';
`$env:PARTITION_RULE='5';
`$env:NODE0_DSN='postgresql://postgres:$PG_PASSWORD_TEXT@localhost:5432/node0db';
`$env:NODE1_DSN='postgresql://postgres:$PG_PASSWORD_TEXT@localhost:5432/node1db';
`$env:NODE2_DSN='postgresql://postgres:$PG_PASSWORD_TEXT@localhost:5432/node2db';
Write-Host 'Node 0 (Central) - Port 8000' -ForegroundColor Cyan;
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"@

Start-Sleep -Seconds 2

Write-Host "Starting Node 1 (Fragment 1-5 - Port 8001)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", @"
cd '$PWD\replication';
.\.venv\Scripts\Activate.ps1;
`$env:DATABASE_DSN='postgresql://postgres:$PG_PASSWORD_TEXT@localhost:5432/node1db';
`$env:NODE_NAME='node1';
`$env:DEFAULT_MASTER='node0';
`$env:DEFAULT_MASTER_URL='http://localhost:8000';
`$env:PEER_NODES='[{\"name\":\"node0\",\"url\":\"http://localhost:8000\"},{\"name\":\"node1\",\"url\":\"http://localhost:8001\"},{\"name\":\"node2\",\"url\":\"http://localhost:8002\"}]';
`$env:POLL_INTERVAL='5';
`$env:APPLIER_INTERVAL='2';
`$env:PROMOTED='false';
`$env:PARTITION_RULE='5';
`$env:NODE0_DSN='postgresql://postgres:$PG_PASSWORD_TEXT@localhost:5432/node0db';
`$env:NODE1_DSN='postgresql://postgres:$PG_PASSWORD_TEXT@localhost:5432/node1db';
`$env:NODE2_DSN='postgresql://postgres:$PG_PASSWORD_TEXT@localhost:5432/node2db';
Write-Host 'Node 1 (Fragment qty 1-5) - Port 8001' -ForegroundColor Cyan;
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
"@

Start-Sleep -Seconds 2

Write-Host "Starting Node 2 (Fragment 6-10 - Port 8002)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", @"
cd '$PWD\replication';
.\.venv\Scripts\Activate.ps1;
`$env:DATABASE_DSN='postgresql://postgres:$PG_PASSWORD_TEXT@localhost:5432/node2db';
`$env:NODE_NAME='node2';
`$env:DEFAULT_MASTER='node0';
`$env:DEFAULT_MASTER_URL='http://localhost:8000';
`$env:PEER_NODES='[{\"name\":\"node0\",\"url\":\"http://localhost:8000\"},{\"name\":\"node1\",\"url\":\"http://localhost:8001\"},{\"name\":\"node2\",\"url\":\"http://localhost:8002\"}]';
`$env:POLL_INTERVAL='5';
`$env:APPLIER_INTERVAL='2';
`$env:PROMOTED='false';
`$env:PARTITION_RULE='5';
`$env:NODE0_DSN='postgresql://postgres:$PG_PASSWORD_TEXT@localhost:5432/node0db';
`$env:NODE1_DSN='postgresql://postgres:$PG_PASSWORD_TEXT@localhost:5432/node1db';
`$env:NODE2_DSN='postgresql://postgres:$PG_PASSWORD_TEXT@localhost:5432/node2db';
Write-Host 'Node 2 (Fragment qty 6-10) - Port 8002' -ForegroundColor Cyan;
uvicorn main:app --host 0.0.0.0 --port 8002 --reload
"@

Write-Host ""
Write-Host "=== All nodes starting in separate windows ===" -ForegroundColor Cyan
Write-Host "Node 0: http://localhost:8000/docs" -ForegroundColor Yellow
Write-Host "Node 1: http://localhost:8001/docs" -ForegroundColor Yellow
Write-Host "Node 2: http://localhost:8002/docs" -ForegroundColor Yellow
Write-Host ""
Write-Host "Press Ctrl+C in each window to stop nodes" -ForegroundColor Gray
