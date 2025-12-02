# Quick Setup Instructions

## For First-Time Setup

1. **Install PostgreSQL** (if not installed)
   - Download from: https://www.postgresql.org/download/windows/
   - Or use: `choco install postgresql`
   - Remember your password!

2. **Create Databases**
   ```powershell
   psql -U postgres
   ```
   Then in psql:
   ```sql
   CREATE DATABASE node0db;
   CREATE DATABASE node1db;
   CREATE DATABASE node2db;
   \q
   ```

3. **Setup Python Environment**
   ```powershell
   cd replication
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

4. **Initialize Database Schema**
   ```powershell
   python init_db.py
   ```
   (Enter your PostgreSQL password when prompted)

5. **Setup Frontend**
   ```powershell
   cd frontend\web-app
   npm install
   ```

## To Run the System

**Option 1: Using Scripts (Easiest)**
```powershell
# Terminal 1: Start all backend nodes
.\start-nodes.ps1

# Terminal 2: Start frontend
.\start-frontend.ps1
```

**Option 2: Manual**
- See `LOCAL_SETUP_GUIDE.md` for detailed instructions

## Access Points

- **Frontend**: http://localhost:5173
- **Node 0 API**: http://localhost:8000/docs
- **Node 1 API**: http://localhost:8001/docs
- **Node 2 API**: http://localhost:8002/docs

## Troubleshooting

- **Execution Policy Error**: Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`
- **Port in Use**: Change ports in start scripts or kill existing processes
- **Connection Refused**: Check PostgreSQL is running with `Get-Service postgresql*`

See `LOCAL_SETUP_GUIDE.md` for complete documentation.
