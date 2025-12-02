# Proxmox VMs Setup Guide for STADVDB MCO2

Complete guide for setting up 3 virtual machines in Proxmox for the distributed database system.

---

## Table of Contents
- [Overview](#overview)
- [VM Specifications](#vm-specifications)
- [Initial VM Setup](#initial-vm-setup)
- [Software Installation](#software-installation)
- [Database Setup](#database-setup)
- [Network Configuration](#network-configuration)
- [Deploy Application Code](#deploy-application-code)
- [Testing Connectivity](#testing-connectivity)
- [Quick Reference Commands](#quick-reference-commands)

---

## Overview

### Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                      PROXMOX HOST                           │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   VM1/Node0  │  │   VM2/Node1  │  │   VM3/Node2  │     │
│  │   (Central)  │  │   (Qty 1-5)  │  │  (Qty 6-10)  │     │
│  │              │  │              │  │              │     │
│  │ PostgreSQL   │  │ PostgreSQL   │  │ PostgreSQL   │     │
│  │ Python API   │  │ Python API   │  │ Python API   │     │
│  │ React App    │  │              │  │              │     │
│  │              │  │              │  │              │     │
│  │ Port: 8000   │  │ Port: 8001   │  │ Port: 8002   │     │
│  │ Port: 3000   │  │              │  │              │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│         │                 │                 │              │
│         └─────────────────┴─────────────────┘              │
│                   Internal Network                         │
│              (10.2.14.0/16 or similar)                     │
└─────────────────────────────────────────────────────────────┘
```

---

## VM Specifications

### Minimum Requirements Per VM

| Component | Specification |
|-----------|--------------|
| **CPU** | 2 cores |
| **RAM** | 2-4 GB |
| **Disk** | 20-30 GB |
| **OS** | Ubuntu Server 22.04 LTS or 24.04 LTS |
| **Network** | Bridged or NAT with port forwarding |

### Recommended Setup

| VM | Name | Role | Ports | Additional Notes |
|----|------|------|-------|------------------|
| VM1 | STADVDB44-Server0 | Central Node + Frontend | 8000, 3000, 5432 | Hosts React app |
| VM2 | STADVDB44-Server1 | Fragment Node 1 | 8001, 5432 | Quantity 1-5 |
| VM3 | STADVDB44-Server2 | Fragment Node 2 | 8002, 5432 | Quantity 6-10 |

---

## Initial VM Setup

### Step 1: Create VMs in Proxmox

**For each of the 3 VMs:**

1. **Access Proxmox Web UI**
   - Navigate to: `https://your-proxmox-server:8006`

2. **Create New VM**
   - Click "Create VM" button
   - **General Tab:**
     - Node: Select your Proxmox node
     - VM ID: `100`, `101`, `102` (or auto)
     - Name: `STADVDB44-Server0`, `STADVDB44-Server1`, `STADVDB44-Server2`
   
   - **OS Tab:**
     - ISO Image: Ubuntu Server 22.04 or 24.04 LTS
     - Guest OS Type: Linux
     - Version: 6.x - 2.6 Kernel

   - **System Tab:**
     - Graphics card: Default
     - Machine: Default (q35)
     - BIOS: Default (SeaBIOS)
     - SCSI Controller: VirtIO SCSI

   - **Disks Tab:**
     - Bus/Device: SCSI
     - Storage: local-lvm (or your storage)
     - Disk size: 25-30 GB
     - Cache: Default (No cache)
     - Discard: ✓ (if using SSD)

   - **CPU Tab:**
     - Sockets: 1
     - Cores: 2
     - Type: host (or kvm64)

   - **Memory Tab:**
     - Memory: 2048-4096 MB
     - Minimum: 1024 MB
     - Ballooning Device: ✓

   - **Network Tab:**
     - Bridge: vmbr0 (or your bridge)
     - Model: VirtIO (paravirtualized)
     - Firewall: ✓ (optional)

3. **Start VM and Install Ubuntu**
   - Select VM → Console
   - Follow Ubuntu installation wizard:
     - Language: English
     - Keyboard: Your layout
     - Network: DHCP (or static IP)
     - Storage: Use entire disk
     - Profile:
       - Name: `stadvdb` or `admin`
       - Server name: `server0`, `server1`, `server2`
       - Username: `stadvdb` (or your choice)
       - Password: (choose a strong password)
     - SSH: ✓ Install OpenSSH server
     - Featured snaps: Skip (install manually later)

4. **Complete Installation**
   - Wait for installation to complete
   - Reboot when prompted
   - Remove installation media (Proxmox does this automatically)

---

### Step 2: Post-Installation Configuration

**On EACH VM after first boot:**

```bash
# Login with your credentials

# Update system packages
sudo apt update
sudo apt upgrade -y

# Install essential tools
sudo apt install -y curl wget vim git net-tools build-essential

# Configure timezone (optional)
sudo timedatectl set-timezone Asia/Manila  # Or your timezone

# Check IP address
ip addr show

# Note down the IP for each VM:
# VM1 (Server0): e.g., 10.2.14.132
# VM2 (Server1): e.g., 10.2.14.133  
# VM3 (Server2): e.g., 10.2.14.134
```

---

### Step 3: Configure SSH Access

**Option A: Password SSH (Easier)**
```bash
# Already enabled during Ubuntu installation
# Test from your laptop:
ssh stadvdb@<VM-IP>
```

**Option B: Key-based SSH (More Secure)**

**On your laptop:**
```powershell
# Generate SSH key (if you don't have one)
ssh-keygen -t ed25519 -C "your_email@example.com"

# Copy public key to each VM
ssh-copy-id stadvdb@<VM1-IP>
ssh-copy-id stadvdb@<VM2-IP>
ssh-copy-id stadvdb@<VM3-IP>

# Test connection
ssh stadvdb@<VM1-IP>
```

---

## Software Installation

### Step 4: Install PostgreSQL 18

**On ALL 3 VMs:**

```bash
# Add PostgreSQL APT repository
sudo sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'

# Import repository signing key
wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -

# Update package list
sudo apt update

# Install PostgreSQL 18
sudo apt install -y postgresql-18 postgresql-contrib-18

# Verify installation
psql --version
# Should show: psql (PostgreSQL) 18.x

# Check service status
sudo systemctl status postgresql

# Check cluster status
pg_lsclusters
# Should show: 18   main   5432   online   postgres
```

**Note the port!** Usually 5432, but could be different. Check with:
```bash
sudo ss -tlnp | grep postgres
# or
sudo grep "^port" /etc/postgresql/18/main/postgresql.conf
```

---

### Step 5: Install Python 3 and Tools

**On ALL 3 VMs:**

```bash
# Install Python 3 and development tools
sudo apt install -y python3 python3-venv python3-pip python3-dev

# Verify Python version
python3 --version
# Should be Python 3.10+ (Ubuntu 22.04) or 3.12+ (Ubuntu 24.04)

# Install build tools for Python packages
sudo apt install -y build-essential libpq-dev

# Upgrade pip
pip3 install --upgrade pip
```

---

### Step 6: Install Node.js (VM1 ONLY)

**On VM1 (Server0) only - for frontend:**

```bash
# Install Node.js 20 LTS
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Verify installation
node --version    # Should show v20.x.x
npm --version     # Should show 10.x.x
```

---

### Step 7: Install Git and GitHub CLI

**On ALL 3 VMs:**

```bash
# Install Git
sudo apt install -y git

# Configure Git (use your details)
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"

# Install GitHub CLI (optional but helpful)
type -p curl >/dev/null || (sudo apt update && sudo apt install curl -y)
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt update
sudo apt install -y gh

# Authenticate with GitHub (if using private repo)
gh auth login
```

---

## Database Setup

### Step 8: Configure PostgreSQL

**On ALL 3 VMs:**

#### 8.1: Configure PostgreSQL for Network Access

```bash
# Edit postgresql.conf
sudo nano /etc/postgresql/18/main/postgresql.conf
```

**Find and modify:**
```conf
# Listen on all interfaces (find the line and uncomment/change)
listen_addresses = '*'

# Verify port
port = 5432
```

**Save:** `Ctrl+X`, `Y`, `Enter`

#### 8.2: Configure Authentication

```bash
# Edit pg_hba.conf
sudo nano /etc/postgresql/18/main/pg_hba.conf
```

**Add these lines BEFORE the existing rules:**
```conf
# TYPE  DATABASE        USER            ADDRESS                 METHOD

# Local connections without password (for convenience)
local   all             all                                     trust

# IPv4 local connections
host    all             all             127.0.0.1/32            trust

# IPv6 local connections
host    all             all             ::1/128                 trust

# Allow VM network (adjust to match your Proxmox network)
host    all             all             10.2.14.0/16            trust

# If your Proxmox uses different network, e.g., 192.168.1.0/24:
# host    all             all             192.168.1.0/24          trust
```

**Save:** `Ctrl+X`, `Y`, `Enter`

#### 8.3: Configure Firewall

```bash
# Check if UFW is active
sudo ufw status

# If active, allow PostgreSQL port from VM network
sudo ufw allow from 10.2.14.0/16 to any port 5432

# Allow SSH (if not already allowed)
sudo ufw allow 22/tcp

# Allow API ports
# On VM1:
sudo ufw allow 8000/tcp
sudo ufw allow 3000/tcp

# On VM2:
sudo ufw allow 8001/tcp

# On VM3:
sudo ufw allow 8002/tcp

# Reload firewall
sudo ufw reload
```

#### 8.4: Restart PostgreSQL

```bash
# Restart PostgreSQL
sudo systemctl restart postgresql

# Verify it's running
sudo systemctl status postgresql

# Check it's listening on all interfaces
sudo ss -tlnp | grep postgres
# Should show 0.0.0.0:5432 or *:5432
```

---

### Step 9: Create Databases

**On EACH VM, create the appropriate database:**

```bash
# Switch to postgres user
sudo -i -u postgres

# Create database
# VM1 (Server0):
createdb node0db

# VM2 (Server1):
createdb node1db

# VM3 (Server2):
createdb node2db

# Verify database was created
psql -c "\l"

# Exit postgres user
exit
```

---

### Step 10: Create Database User (Optional but Recommended)

**On ALL VMs:**

```bash
# Create app user with password
sudo -u postgres psql <<'SQL'
CREATE ROLE app_user WITH LOGIN PASSWORD 'your_secure_password';
SQL

# Grant permissions (after tables are created, see Step 12)
```

---

## Network Configuration

### Step 11: Configure Network & Test Connectivity

#### 11.1: Get VM IP Addresses

**On EACH VM:**
```bash
# Get IP address
ip addr show | grep "inet "

# Or simpler:
hostname -I
```

**Note down IPs:**
- VM1 (Server0): `__________`
- VM2 (Server1): `__________`
- VM3 (Server2): `__________`

#### 11.2: Test Network Connectivity Between VMs

**From VM1:**
```bash
# Ping VM2
ping -c 3 <VM2-IP>

# Ping VM3
ping -c 3 <VM3-IP>

# Test PostgreSQL connection to VM2
psql -h <VM2-IP> -p 5432 -U postgres -d node1db -c "SELECT 1;"

# Test PostgreSQL connection to VM3
psql -h <VM3-IP> -p 5432 -U postgres -d node2db -c "SELECT 1;"
```

**Expected Result:** All connections should succeed.

**If connections fail:**
- Check firewall: `sudo ufw status`
- Check PostgreSQL is listening: `sudo ss -tlnp | grep postgres`
- Check pg_hba.conf has correct network range
- Restart PostgreSQL: `sudo systemctl restart postgresql`

---

## Deploy Application Code

### Step 12: Clone Repository

**On ALL 3 VMs:**

```bash
# Navigate to home directory
cd ~

# Clone repository
git clone https://github.com/zuraxy/STADVDB.git

# Navigate to project
cd STADVDB

# Switch to correct branch
git checkout MCO2.main  # or your branch

# Verify files
ls -la
```

---

### Step 13: Setup Python Backend

**On ALL 3 VMs:**

```bash
# Navigate to replication folder
cd ~/STADVDB/replication

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Verify installation
pip list
```

---

### Step 14: Initialize Database Schema

**On EACH VM, run the initialization script:**

```bash
# Make sure you're in the replication folder with venv activated
cd ~/STADVDB/replication
source .venv/bin/activate

# Create initialization script
nano init_schema.py
```

**Paste this content:**
```python
import asyncio
import asyncpg

async def init_db():
    # Connect to database
    # Change database name for each VM:
    # VM1: node0db
    # VM2: node1db
    # VM3: node2db
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='postgres',
        database='node0db'  # Change this!
    )
    
    # Create orders table
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            quantity int NOT NULL,
            payload jsonb,
            created_at timestamptz DEFAULT now(),
            updated_at timestamptz DEFAULT now()
        );
    """)
    
    # Create op_log table
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS op_log (
            op_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            origin_node text NOT NULL,
            op_type text NOT NULL,
            table_name text NOT NULL,
            row_id uuid NOT NULL,
            payload jsonb,
            ts timestamptz DEFAULT now(),
            lamport bigint DEFAULT 0,
            applied boolean DEFAULT false,
            applied_ts timestamptz
        );
        
        CREATE INDEX IF NOT EXISTS idx_oplog_origin_ts ON op_log(origin_node, ts);
        CREATE INDEX IF NOT EXISTS idx_oplog_lamport ON op_log(lamport);
        CREATE INDEX IF NOT EXISTS idx_oplog_applied ON op_log(applied) WHERE NOT applied;
    """)
    
    # Create log_acknowledgements table
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS log_acknowledgements (
            op_id uuid REFERENCES op_log(op_id) ON DELETE CASCADE,
            node text NOT NULL,
            ack_ts timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (op_id, node)
        );
    """)
    
    # Apply constraints based on node
    # UNCOMMENT THE APPROPRIATE SECTION FOR EACH VM:
    
    # VM2 ONLY - Quantity 1-5:
    # await conn.execute("""
    #     ALTER TABLE orders 
    #     DROP CONSTRAINT IF EXISTS qty_1to5;
    #     
    #     ALTER TABLE orders 
    #     ADD CONSTRAINT qty_1to5 CHECK (quantity >= 1 AND quantity <= 5);
    # """)
    
    # VM3 ONLY - Quantity 6-10:
    # await conn.execute("""
    #     ALTER TABLE orders 
    #     DROP CONSTRAINT IF EXISTS qty_6to10;
    #     
    #     ALTER TABLE orders 
    #     ADD CONSTRAINT qty_6to10 CHECK (quantity >= 6 AND quantity <= 10);
    # """)
    
    # Grant permissions to app_user (if created)
    await conn.execute("""
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE orders TO app_user;
        GRANT SELECT, INSERT, UPDATE ON TABLE op_log TO app_user;
        GRANT SELECT, INSERT ON TABLE log_acknowledgements TO app_user;
        GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO app_user;
    """)
    
    await conn.close()
    print("✅ Database schema initialized successfully!")

if __name__ == "__main__":
    asyncio.run(init_db())
```

**Save:** `Ctrl+X`, `Y`, `Enter`

**Run it:**
```bash
python init_schema.py
```

---

### Step 15: Configure Environment Variables

**On EACH VM, create a .env file:**

```bash
cd ~/STADVDB/replication
nano .env
```

**VM1 (Server0) - .env:**
```env
DATABASE_DSN=postgresql://postgres@localhost:5432/node0db
NODE_NAME=node0
DEFAULT_MASTER=node0
DEFAULT_MASTER_URL=http://<VM1-IP>:8000
PEER_NODES=[{"name":"node0","url":"http://<VM1-IP>:8000"},{"name":"node1","url":"http://<VM2-IP>:8001"},{"name":"node2","url":"http://<VM3-IP>:8002"}]
POLL_INTERVAL=5
APPLIER_INTERVAL=2
PROMOTED=false
PARTITION_RULE=5
NODE0_DSN=postgresql://postgres@<VM1-IP>:5432/node0db
NODE1_DSN=postgresql://postgres@<VM2-IP>:5432/node1db
NODE2_DSN=postgresql://postgres@<VM3-IP>:5432/node2db
```

**VM2 (Server1) - .env:**
```env
DATABASE_DSN=postgresql://postgres@localhost:5432/node1db
NODE_NAME=node1
DEFAULT_MASTER=node0
DEFAULT_MASTER_URL=http://<VM1-IP>:8000
PEER_NODES=[{"name":"node0","url":"http://<VM1-IP>:8000"},{"name":"node1","url":"http://<VM2-IP>:8001"},{"name":"node2","url":"http://<VM3-IP>:8002"}]
POLL_INTERVAL=5
APPLIER_INTERVAL=2
PROMOTED=false
PARTITION_RULE=5
NODE0_DSN=postgresql://postgres@<VM1-IP>:5432/node0db
NODE1_DSN=postgresql://postgres@<VM2-IP>:5432/node1db
NODE2_DSN=postgresql://postgres@<VM3-IP>:5432/node2db
```

**VM3 (Server2) - .env:**
```env
DATABASE_DSN=postgresql://postgres@localhost:5432/node2db
NODE_NAME=node2
DEFAULT_MASTER=node0
DEFAULT_MASTER_URL=http://<VM1-IP>:8000
PEER_NODES=[{"name":"node0","url":"http://<VM1-IP>:8000"},{"name":"node1","url":"http://<VM2-IP>:8001"},{"name":"node2","url":"http://<VM3-IP>:8002"}]
POLL_INTERVAL=5
APPLIER_INTERVAL=2
PROMOTED=false
PARTITION_RULE=5
NODE0_DSN=postgresql://postgres@<VM1-IP>:5432/node0db
NODE1_DSN=postgresql://postgres@<VM2-IP>:5432/node1db
NODE2_DSN=postgresql://postgres@<VM3-IP>:5432/node2db
```

**Replace `<VM1-IP>`, `<VM2-IP>`, `<VM3-IP>` with your actual IPs!**

---

### Step 16: Create Systemd Service (Auto-start Backend)

**On ALL 3 VMs:**

```bash
# Create systemd service file
sudo nano /etc/systemd/system/replication.service
```

**Content (adjust ExecStart path and port for each VM):**

**VM1:**
```ini
[Unit]
Description=STADVDB Replication Service (Node 0)
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=stadvdb
WorkingDirectory=/home/stadvdb/STADVDB/replication
Environment="PATH=/home/stadvdb/STADVDB/replication/.venv/bin:/usr/bin"
EnvironmentFile=/home/stadvdb/STADVDB/replication/.env
ExecStart=/home/stadvdb/STADVDB/replication/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**VM2:** (Change port to 8001, User to match your username)
**VM3:** (Change port to 8002, User to match your username)

**Save and enable:**
```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable replication

# Start service
sudo systemctl start replication

# Check status
sudo systemctl status replication

# View logs
sudo journalctl -u replication -n 50 -f
```

---

### Step 17: Setup Frontend (VM1 ONLY)

**On VM1:**

```bash
# Navigate to frontend folder
cd ~/STADVDB/frontend/web-app

# Install dependencies
npm install

# Create .env file
nano .env
```

**Content:**
```env
VITE_API_URL=http://<VM1-IP>:8000
```

**Build frontend:**
```bash
# Development mode (for testing):
npm run dev

# Production build:
npm run build
```

**Setup frontend service (optional):**
```bash
sudo nano /etc/systemd/system/frontend.service
```

**Content:**
```ini
[Unit]
Description=STADVDB Frontend Service
After=network.target

[Service]
Type=simple
User=stadvdb
WorkingDirectory=/home/stadvdb/STADVDB/frontend/web-app
Environment="PATH=/usr/bin"
ExecStart=/usr/bin/npm run dev -- --host 0.0.0.0
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Enable and start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable frontend
sudo systemctl start frontend
sudo systemctl status frontend
```

---

## Testing Connectivity

### Step 18: Test Everything

**From your laptop:**

```powershell
# Test Node 0 health
curl http://<VM1-IP>:8000/health

# Test Node 1 health
curl http://<VM2-IP>:8001/health

# Test Node 2 health
curl http://<VM3-IP>:8002/health

# Access API documentation
# Open in browser:
# http://<VM1-IP>:8000/docs
# http://<VM2-IP>:8001/docs
# http://<VM3-IP>:8002/docs

# Access frontend
# http://<VM1-IP>:5173
```

**Test replication:**
```bash
# Create order on Node 0
curl -X POST http://<VM1-IP>:8000/orders \
  -H "Content-Type: application/json" \
  -d '{"quantity": 3, "payload": {"test": "data"}}'

# Check if it replicated to Node 1
curl http://<VM2-IP>:8001/orders

# Check replication status
curl http://<VM1-IP>:8000/status/replication
```

---

## Quick Reference Commands

### Check Service Status
```bash
# Backend
sudo systemctl status replication

# Frontend (VM1 only)
sudo systemctl status frontend

# PostgreSQL
sudo systemctl status postgresql
```

### View Logs
```bash
# Backend logs (live)
sudo journalctl -u replication -f

# Backend logs (last 50 lines)
sudo journalctl -u replication -n 50

# PostgreSQL logs
sudo tail -f /var/log/postgresql/postgresql-18-main.log
```

### Restart Services
```bash
# Restart backend
sudo systemctl restart replication

# Restart PostgreSQL
sudo systemctl restart postgresql

# Restart frontend
sudo systemctl restart frontend
```

### Update Code
```bash
# Pull latest changes
cd ~/STADVDB
git pull

# Restart backend
sudo systemctl restart replication

# Restart frontend (if changed)
cd frontend/web-app
npm install
sudo systemctl restart frontend
```

### Database Commands
```bash
# Connect to database
psql -U postgres -d node0db  # or node1db, node2db

# List tables
\dt

# Describe table
\d orders

# Count rows
SELECT COUNT(*) FROM orders;

# Exit psql
\q
```

---

## Port Forwarding (If Using NAT Network)

If your Proxmox VMs are behind NAT, you'll need port forwarding:

**Example forwarding rules (configure in Proxmox or router):**

| External Port | VM | Internal Port | Service |
|---------------|----|--------------:|---------|
| 60532 | VM1 | 22 | SSH |
| 60533 | VM2 | 22 | SSH |
| 60534 | VM3 | 22 | SSH |
| 8000 | VM1 | 8000 | API Node 0 |
| 8001 | VM2 | 8001 | API Node 1 |
| 8002 | VM3 | 8002 | API Node 2 |
| 3000 | VM1 | 5173 | Frontend |

---

## Troubleshooting

### Common Issues

**1. Can't connect to VM**
```bash
# Check VM is running in Proxmox
# Check SSH service
sudo systemctl status ssh

# Check firewall
sudo ufw status
```

**2. PostgreSQL won't start**
```bash
# Check logs
sudo journalctl -u postgresql -n 50

# Check configuration
sudo nano /etc/postgresql/18/main/postgresql.conf

# Check port conflicts
sudo ss -tlnp | grep 5432
```

**3. Backend service fails**
```bash
# Check logs
sudo journalctl -u replication -n 100

# Test manually
cd ~/STADVDB/replication
source .venv/bin/activate
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

**4. VMs can't communicate**
```bash
# Check firewall on each VM
sudo ufw status

# Test ping
ping <other-VM-IP>

# Test PostgreSQL connection
psql -h <other-VM-IP> -U postgres -d node0db -c "SELECT 1;"
```

---

## Next Steps

After setup is complete:
1. See `DEPLOYMENT.md` for deployment strategies
2. See `VM_UPDATE_GUIDE.md` for updating code on VMs
3. See `START_HERE.md` for running the system locally
4. Test concurrency scenarios for your MCO2 report
5. Test recovery scenarios for your MCO2 report

---

**🎉 Your Proxmox VMs are now ready for STADVDB MCO2!**
