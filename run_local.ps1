# Local Development Runner for Recovery Subsystem
# Run this script in PowerShell to start the local server

Write-Host "=== STADVDB Local Development Setup ===" -ForegroundColor Cyan

# Set environment variables
$env:DATABASE_DSN = "postgresql://postgres:postgres@localhost:5432/orders"
$env:NODE_NAME = "node0"
$env:DEFAULT_MASTER = "node0"
$env:DEFAULT_MASTER_URL = "http://localhost:8000"
$env:PEER_NODES = '[{"name":"node1","url":"http://localhost:8001"},{"name":"node2","url":"http://localhost:8002"}]'
$env:POLL_INTERVAL = "5"
$env:APPLIER_INTERVAL = "2"
$env:PROMOTED = "false"
$env:PARTITION_RULE = "5"

Write-Host ""
Write-Host "Environment variables set:" -ForegroundColor Green
Write-Host "  DATABASE_DSN: $env:DATABASE_DSN"
Write-Host "  NODE_NAME: $env:NODE_NAME"
Write-Host ""

# Check if database exists
Write-Host "Checking database connection..." -ForegroundColor Yellow
$dbCheck = psql -U postgres -d orders -c "SELECT 1;" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Database 'orders' not found or connection failed." -ForegroundColor Red
    Write-Host "Creating database..." -ForegroundColor Yellow
    psql -U postgres -c "CREATE DATABASE orders;"
}

# Create tables if they don't exist
Write-Host "Setting up tables..." -ForegroundColor Yellow
$setupSQL = @"
CREATE TABLE IF NOT EXISTS orders (
    order_id UUID PRIMARY KEY,
    quantity INTEGER NOT NULL CHECK (quantity >= 1),
    payload JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS op_log (
    op_id UUID PRIMARY KEY,
    origin_node TEXT NOT NULL,
    op_type TEXT NOT NULL,
    table_name TEXT NOT NULL,
    row_id UUID NOT NULL,
    payload JSONB,
    ts TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    lamport BIGINT NOT NULL,
    applied BOOLEAN DEFAULT FALSE,
    applied_ts TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS log_acknowledgements (
    op_id UUID NOT NULL,
    node TEXT NOT NULL,
    ack_ts TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (op_id, node)
);

CREATE TABLE IF NOT EXISTS replication_cursors (
    node TEXT PRIMARY KEY,
    last_lamport BIGINT NOT NULL
);
"@

psql -U postgres -d orders -c $setupSQL

Write-Host ""
Write-Host "Starting FastAPI server on http://localhost:8000 ..." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop" -ForegroundColor Gray
Write-Host ""

# Change to replication directory and run
Set-Location -Path "$PSScriptRoot\replication"
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
