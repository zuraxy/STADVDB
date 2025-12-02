# Local Development Setup Guide

This guide will help you run the distributed database system locally on your Windows machine for testing and development.

## Prerequisites ✅

- ✅ Python 3.13.5 installed
- ✅ Node.js v22.17.0 installed
- PostgreSQL needed (we'll install it)

---

## Part 1: Install PostgreSQL Locally

### Option A: PostgreSQL Installer (Recommended)

1. Download PostgreSQL 16 or 17 from: https://www.postgresql.org/download/windows/
2. Run installer, set password for `postgres` user (remember this!)
3. Default port: `5432`
4. Include pgAdmin 4 (GUI tool)

### Option B: Using Chocolatey

```powershell
choco install postgresql
```

### Verify Installation

```powershell
# Check if PostgreSQL is running
Get-Service postgresql*

# Check version
psql --version
```

---

## Part 2: Create Local Databases

Open PowerShell as Administrator and run:

```powershell
# Connect to PostgreSQL (enter your password when prompted)
psql -U postgres

# Inside psql, create 3 databases:
CREATE DATABASE node0db;
CREATE DATABASE node1db;
CREATE DATABASE node2db;

# List databases to verify
\l

# Exit psql
\q
```

---

## Part 3: Setup Python Backend (Replication Service)

```powershell
# Navigate to project root
cd "C:\Users\enzch\Documents\STADVDB - MCO2"

# Create virtual environment for Python
cd replication
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# If you get execution policy error, run:
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Install dependencies
pip install -r requirements.txt

# Verify installation
pip list
```

---

## Part 4: Configure Environment Variables

### Create `.env` file for each node

**For Node 0 (Central):**

Create `replication\.env.node0`:

```env
DATABASE_DSN=postgresql://postgres:YOUR_PASSWORD@localhost:5432/node0db
NODE_NAME=node0
DEFAULT_MASTER=node0
DEFAULT_MASTER_URL=http://localhost:8000
PEER_NODES=[{"name":"node0","url":"http://localhost:8000"},{"name":"node1","url":"http://localhost:8001"},{"name":"node2","url":"http://localhost:8002"}]
POLL_INTERVAL=5
APPLIER_INTERVAL=2
PROMOTED=false
PARTITION_RULE=5
NODE0_DSN=postgresql://postgres:YOUR_PASSWORD@localhost:5432/node0db
NODE1_DSN=postgresql://postgres:YOUR_PASSWORD@localhost:5432/node1db
NODE2_DSN=postgresql://postgres:YOUR_PASSWORD@localhost:5432/node2db
```

**For Node 1 (Fragment 1-5):**

Create `replication\.env.node1`:

```env
DATABASE_DSN=postgresql://postgres:YOUR_PASSWORD@localhost:5432/node1db
NODE_NAME=node1
DEFAULT_MASTER=node0
DEFAULT_MASTER_URL=http://localhost:8000
PEER_NODES=[{"name":"node0","url":"http://localhost:8000"},{"name":"node1","url":"http://localhost:8001"},{"name":"node2","url":"http://localhost:8002"}]
POLL_INTERVAL=5
APPLIER_INTERVAL=2
PROMOTED=false
PARTITION_RULE=5
NODE0_DSN=postgresql://postgres:YOUR_PASSWORD@localhost:5432/node0db
NODE1_DSN=postgresql://postgres:YOUR_PASSWORD@localhost:5432/node1db
NODE2_DSN=postgresql://postgres:YOUR_PASSWORD@localhost:5432/node2db
```

**For Node 2 (Fragment 6-10):**

Create `replication\.env.node2`:

```env
DATABASE_DSN=postgresql://postgres:YOUR_PASSWORD@localhost:5432/node2db
NODE_NAME=node2
DEFAULT_MASTER=node0
DEFAULT_MASTER_URL=http://localhost:8000
PEER_NODES=[{"name":"node0","url":"http://localhost:8000"},{"name":"node1","url":"http://localhost:8001"},{"name":"node2","url":"http://localhost:8002"}]
POLL_INTERVAL=5
APPLIER_INTERVAL=2
PROMOTED=false
PARTITION_RULE=5
NODE0_DSN=postgresql://postgres:YOUR_PASSWORD@localhost:5432/node0db
NODE1_DSN=postgresql://postgres:YOUR_PASSWORD@localhost:5432/node1db
NODE2_DSN=postgresql://postgres:YOUR_PASSWORD@localhost:5432/node2db
```

**Replace `YOUR_PASSWORD` with your actual PostgreSQL password!**

---

## Part 5: Initialize Database Schema

```powershell
# Make sure you're in replication folder with venv activated
cd "C:\Users\enzch\Documents\STADVDB - MCO2\replication"
.\.venv\Scripts\Activate.ps1

# Run initialization script (we'll create this)
python init.py
```

---

## Part 6: Setup Frontend

```powershell
# Navigate to frontend folder
cd "C:\Users\enzch\Documents\STADVDB - MCO2\frontend\web-app"

# Install dependencies
npm install

# Create .env file
# Copy .env.example to .env
Copy-Item .env.example .env

# Edit .env to point to your local backend
# VITE_API_URL=http://localhost:8000
```

---

## Part 7: Running the System

You'll need **4 terminal windows**:

### Terminal 1: Node 0 (Port 8000)

```powershell
cd "C:\Users\enzch\Documents\STADVDB - MCO2\replication"
.\.venv\Scripts\Activate.ps1

# Load Node 0 config and start
$env:DATABASE_DSN="postgresql://postgres:YOUR_PASSWORD@localhost:5432/node0db"
$env:NODE_NAME="node0"
$env:DEFAULT_MASTER="node0"
$env:DEFAULT_MASTER_URL="http://localhost:8000"
$env:PEER_NODES='[{"name":"node0","url":"http://localhost:8000"},{"name":"node1","url":"http://localhost:8001"},{"name":"node2","url":"http://localhost:8002"}]'
$env:POLL_INTERVAL="5"
$env:APPLIER_INTERVAL="2"
$env:PROMOTED="false"
$env:PARTITION_RULE="5"
$env:NODE0_DSN="postgresql://postgres:YOUR_PASSWORD@localhost:5432/node0db"
$env:NODE1_DSN="postgresql://postgres:YOUR_PASSWORD@localhost:5432/node1db"
$env:NODE2_DSN="postgresql://postgres:YOUR_PASSWORD@localhost:5432/node2db"

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Terminal 2: Node 1 (Port 8001)

```powershell
cd "C:\Users\enzch\Documents\STADVDB - MCO2\replication"
.\.venv\Scripts\Activate.ps1

$env:DATABASE_DSN="postgresql://postgres:YOUR_PASSWORD@localhost:5432/node1db"
$env:NODE_NAME="node1"
$env:DEFAULT_MASTER="node0"
$env:DEFAULT_MASTER_URL="http://localhost:8000"
$env:PEER_NODES='[{"name":"node0","url":"http://localhost:8000"},{"name":"node1","url":"http://localhost:8001"},{"name":"node2","url":"http://localhost:8002"}]'
$env:POLL_INTERVAL="5"
$env:APPLIER_INTERVAL="2"
$env:PROMOTED="false"
$env:PARTITION_RULE="5"
$env:NODE0_DSN="postgresql://postgres:YOUR_PASSWORD@localhost:5432/node0db"
$env:NODE1_DSN="postgresql://postgres:YOUR_PASSWORD@localhost:5432/node1db"
$env:NODE2_DSN="postgresql://postgres:YOUR_PASSWORD@localhost:5432/node2db"

uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

### Terminal 3: Node 2 (Port 8002)

```powershell
cd "C:\Users\enzch\Documents\STADVDB - MCO2\replication"
.\.venv\Scripts\Activate.ps1

$env:DATABASE_DSN="postgresql://postgres:YOUR_PASSWORD@localhost:5432/node2db"
$env:NODE_NAME="node2"
$env:DEFAULT_MASTER="node0"
$env:DEFAULT_MASTER_URL="http://localhost:8000"
$env:PEER_NODES='[{"name":"node0","url":"http://localhost:8000"},{"name":"node1","url":"http://localhost:8001"},{"name":"node2","url":"http://localhost:8002"}]'
$env:POLL_INTERVAL="5"
$env:APPLIER_INTERVAL="2"
$env:PROMOTED="false"
$env:PARTITION_RULE="5"
$env:NODE0_DSN="postgresql://postgres:YOUR_PASSWORD@localhost:5432/node0db"
$env:NODE1_DSN="postgresql://postgres:YOUR_PASSWORD@localhost:5432/node1db"
$env:NODE2_DSN="postgresql://postgres:YOUR_PASSWORD@localhost:5432/node2db"

uvicorn main:app --host 0.0.0.0 --port 8002 --reload
```

### Terminal 4: Frontend

```powershell
cd "C:\Users\enzch\Documents\STADVDB - MCO2\frontend\web-app"
npm run dev
```

---

## Part 8: Verify Everything Works

1. **Backend APIs**: 
   - http://localhost:8000/docs (Node 0)
   - http://localhost:8001/docs (Node 1)
   - http://localhost:8002/docs (Node 2)

2. **Frontend**: http://localhost:5173

3. **Test Health**:
   - http://localhost:8000/health
   - http://localhost:8001/health
   - http://localhost:8002/health

4. **Test Replication Status**:
   - http://localhost:8000/status/replication

---

## Quick Start Scripts (Easier Way!)

I'll create PowerShell scripts to make this easier. Just run:

```powershell
# Start all 3 nodes
.\start-nodes.ps1

# In another terminal, start frontend
.\start-frontend.ps1
```

---

## Troubleshooting

### "execution policy" error
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### "uvicorn: command not found"
```powershell
# Make sure venv is activated
.\.venv\Scripts\Activate.ps1

# Reinstall uvicorn
pip install uvicorn[standard]
```

### "psql: command not found"
Add PostgreSQL to PATH:
- Default location: `C:\Program Files\PostgreSQL\16\bin`

### Port already in use
```powershell
# Find process using port 8000
Get-NetTCPConnection -LocalPort 8000 | Select-Object OwningProcess
# Kill it
Stop-Process -Id <PID>
```

### Database connection refused
- Check PostgreSQL service is running
- Verify password in .env files
- Check port is 5432
