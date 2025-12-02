# PowerShell script to start frontend
# Usage: .\start-frontend.ps1

Write-Host "=== Starting Frontend Application ===" -ForegroundColor Cyan
Write-Host ""

# Navigate to frontend directory
cd "frontend\web-app"

# Check if node_modules exists
if (-not (Test-Path "node_modules")) {
    Write-Host "Installing frontend dependencies..." -ForegroundColor Yellow
    npm install
}

# Check if .env exists, if not create from example
if (-not (Test-Path ".env")) {
    Write-Host "Creating .env file..." -ForegroundColor Yellow
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
    } else {
        # Create basic .env
        "VITE_API_URL=http://localhost:8000" | Out-File -FilePath ".env" -Encoding utf8
    }
}

Write-Host "Starting Vite dev server..." -ForegroundColor Green
Write-Host "Frontend will be available at: http://localhost:5173" -ForegroundColor Yellow
Write-Host ""

npm run dev
