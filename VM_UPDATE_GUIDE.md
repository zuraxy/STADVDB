# VM Update Guide

Quick reference for updating backend and frontend on VMs after pushing code to GitHub.

---

## Table of Contents

- [Update Python Backend (All VMs)](#update-python-backend-all-vms)
- [Update Frontend (VM1 Only)](#update-frontend-vm1-only)
- [Update Both Backend and Frontend](#update-both-backend-and-frontend)
- [Update All VMs at Once (From Laptop)](#update-all-vms-at-once-from-laptop)
- [Troubleshooting](#troubleshooting)

---

## Update Python Backend (All VMs)

### Quick Command (One-Liner)

```bash
cd ~/STADVDB && git pull && cd replication && source .venv/bin/activate && pip install -r requirements.txt && sudo systemctl restart replication && sleep 2 && sudo systemctl status replication
```

### Step-by-Step

```bash
# SSH into VM
ssh root@ccscloud.dlsu.edu.ph -p 60532  # VM1
# ssh root@ccscloud.dlsu.edu.ph -p 60533  # VM2
# ssh root@ccscloud.dlsu.edu.ph -p 60534  # VM3

# Navigate to project
cd ~/STADVDB

# Pull latest code
git pull origin MCO2.main  # or your branch name

# Update Python dependencies
cd replication
source .venv/bin/activate
pip install -r requirements.txt

# Restart service
sudo systemctl restart replication

# Verify it's running
sudo systemctl status replication

# Check logs
sudo journalctl -u replication -n 50 --no-pager

# Test endpoint
curl http://localhost:8000/health  # VM1 (port 8000)
# curl http://localhost:8001/health  # VM2 (port 8001)
# curl http://localhost:8002/health  # VM3 (port 8002)
```

### Using Update Script (Recommended)

Create once:

```bash
nano ~/update-backend.sh
```

Paste:

```bash
#!/bin/bash
set -e

echo "🔄 Updating Python Backend..."

cd ~/STADVDB
echo "📥 Pulling latest changes..."
git pull

cd replication
echo "📦 Installing dependencies..."
source .venv/bin/activate
pip install -r requirements.txt --quiet

echo "🔄 Restarting service..."
sudo systemctl restart replication
sleep 3

echo "✅ Update complete!"
echo ""
echo "📊 Service status:"
sudo systemctl status replication --no-pager -l

echo ""
echo "🧪 Testing endpoint:"
PORT=$(grep -oP 'port \K[0-9]+' /etc/systemd/system/replication.service || echo "8000")
curl -s http://localhost:$PORT/health | python3 -m json.tool || curl http://localhost:$PORT/health

echo ""
echo "📝 Recent logs:"
sudo journalctl -u replication -n 20 --no-pager
```

Make executable:

```bash
chmod +x ~/update-backend.sh
```

Usage:

```bash
~/update-backend.sh
```

---

## Update Frontend (VM1 Only)

Frontend only needs to be updated on **VM1** since it serves the static files via Nginx.

### Quick Command

```bash
cd ~/STADVDB && git pull && cd frontend/web-app && npm install && npm run build && sudo cp -r dist/* /var/www/stadvdb/ && sudo systemctl reload nginx
```

### Step-by-Step

```bash
# SSH into VM1
ssh root@ccscloud.dlsu.edu.ph -p 60532

# Navigate to project
cd ~/STADVDB

# Pull latest code
git pull origin MCO2.main

# Navigate to frontend
cd frontend/web-app

# Install dependencies (if package.json changed)
npm install

# Build production bundle
npm run build

# Copy to web server directory
sudo cp -r dist/* /var/www/stadvdb/

# Reload Nginx (zero downtime)
sudo systemctl reload nginx

# Verify Nginx is running
sudo systemctl status nginx

# Check Nginx logs
sudo tail -n 20 /var/log/nginx/error.log
```

### Using Update Script

Create once:

```bash
nano ~/update-frontend.sh
```

Paste:

```bash
#!/bin/bash
set -e

echo "🎨 Updating Frontend..."

cd ~/STADVDB
echo "📥 Pulling latest changes..."
git pull

cd frontend/web-app
echo "📦 Installing dependencies..."
npm install

echo "🏗️ Building production bundle..."
npm run build

echo "📂 Copying to web server..."
sudo cp -r dist/* /var/www/stadvdb/

echo "🔄 Reloading Nginx..."
sudo systemctl reload nginx

echo "✅ Frontend updated!"
echo ""
echo "📊 Nginx status:"
sudo systemctl status nginx --no-pager -l

echo ""
echo "📝 Recent Nginx logs:"
sudo tail -n 20 /var/log/nginx/access.log
```

Make executable:

```bash
chmod +x ~/update-frontend.sh
```

Usage:

```bash
~/update-frontend.sh
```

---

## Update Both Backend and Frontend

### On VM1 (Has Both)

```bash
cd ~/STADVDB && \
git pull && \
cd replication && source .venv/bin/activate && pip install -r requirements.txt && \
sudo systemctl restart replication && \
cd ../frontend/web-app && npm install && npm run build && \
sudo cp -r dist/* /var/www/stadvdb/ && \
sudo systemctl reload nginx && \
echo "✅ Both backend and frontend updated!"
```

### Using Combined Script

Create once:

```bash
nano ~/update-all.sh
```

Paste:

```bash
#!/bin/bash
set -e

echo "🚀 Updating Backend and Frontend..."

cd ~/STADVDB
echo "📥 Pulling latest changes..."
git pull

# Update Backend
echo ""
echo "🔧 Updating Backend..."
cd replication
source .venv/bin/activate
pip install -r requirements.txt --quiet
sudo systemctl restart replication

# Update Frontend
echo ""
echo "🎨 Updating Frontend..."
cd ../frontend/web-app
npm install
npm run build
sudo cp -r dist/* /var/www/stadvdb/
sudo systemctl reload nginx

echo ""
echo "✅ All updates complete!"
echo ""

# Show status
echo "📊 Backend status:"
sudo systemctl status replication --no-pager -l

echo ""
echo "📊 Nginx status:"
sudo systemctl status nginx --no-pager -l

echo ""
echo "🧪 Testing endpoints:"
curl -s http://localhost:8000/health | python3 -m json.tool || curl http://localhost:8000/health

echo ""
echo "📝 Recent backend logs:"
sudo journalctl -u replication -n 10 --no-pager

echo ""
echo "📝 Recent Nginx logs:"
sudo tail -n 10 /var/log/nginx/access.log
```

Make executable:

```bash
chmod +x ~/update-all.sh
```

Usage:

```bash
~/update-all.sh
```

---

## Update All VMs at Once (From Laptop)

### PowerShell Script (Windows)

Save as `update-all-vms.ps1` on your laptop:

```powershell
Write-Host "🚀 Updating all VMs..." -ForegroundColor Cyan

$vms = @(
    @{Port=60532; Name="VM1 (Node0)"; ApiPort=8000; HasFrontend=$true},
    @{Port=60533; Name="VM2 (Node1)"; ApiPort=8001; HasFrontend=$false},
    @{Port=60534; Name="VM3 (Node2)"; ApiPort=8002; HasFrontend=$false}
)

foreach ($vm in $vms) {
    Write-Host "`n========================================" -ForegroundColor Yellow
    Write-Host "📡 Updating $($vm.Name)..." -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Yellow
    
    # Update backend on all VMs
    Write-Host "🔧 Updating Python backend..." -ForegroundColor Gray
    ssh root@ccscloud.dlsu.edu.ph -p $($vm.Port) @"
cd ~/STADVDB && \
git pull && \
cd replication && \
source .venv/bin/activate && \
pip install -r requirements.txt --quiet && \
sudo systemctl restart replication && \
sleep 2
"@
    
    # Update frontend only on VM1
    if ($vm.HasFrontend) {
        Write-Host "🎨 Updating frontend..." -ForegroundColor Gray
        ssh root@ccscloud.dlsu.edu.ph -p $($vm.Port) @"
cd ~/STADVDB/frontend/web-app && \
npm install && \
npm run build && \
sudo cp -r dist/* /var/www/stadvdb/ && \
sudo systemctl reload nginx
"@
    }
    
    # Check status
    Write-Host "✅ Verifying $($vm.Name)..." -ForegroundColor Green
    ssh root@ccscloud.dlsu.edu.ph -p $($vm.Port) @"
echo '📊 Backend status:' && \
sudo systemctl status replication --no-pager -l | head -3 && \
echo '' && \
echo '🧪 Testing API:' && \
curl -s http://localhost:$($vm.ApiPort)/health
"@
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ $($vm.Name) updated successfully" -ForegroundColor Green
    } else {
        Write-Host "❌ $($vm.Name) update failed" -ForegroundColor Red
    }
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "🎉 All VMs updated!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
```

**Usage:**

```powershell
cd "d:\CCS Files\STADVDB\STADVDB"
.\update-all-vms.ps1
```

---

## Troubleshooting

### Issue 1: Merge Conflicts

```bash
cd ~/STADVDB
git status  # See which files have conflicts

# Option A: Keep remote changes (discard local changes)
git reset --hard origin/MCO2.main

# Option B: Resolve manually
nano file-with-conflict.py
# Fix conflicts, then:
git add .
git commit -m "Resolved merge conflicts"
```

### Issue 2: Backend Service Won't Start

```bash
# Check detailed logs
sudo journalctl -u replication -n 100 --no-pager

# Common fixes:

# 1. Check Python syntax
cd ~/STADVDB/replication
source .venv/bin/activate
python3 -c "import replication.main"

# 2. Reinstall dependencies
pip install -r requirements.txt --upgrade

# 3. Check database connection
PGPASSWORD=postgres psql -h localhost -p 3306 -U postgres -d node0db -c "SELECT 1;"

# 4. Check port not in use
sudo netstat -tlnp | grep 8000

# 5. Restart service
sudo systemctl restart replication
```

### Issue 3: Frontend Not Updating

```bash
# Clear cache and rebuild
cd ~/STADVDB/frontend/web-app
rm -rf node_modules package-lock.json dist
npm install
npm run build
sudo cp -r dist/* /var/www/stadvdb/

# Clear Nginx cache
sudo systemctl reload nginx

# Check Nginx errors
sudo tail -f /var/log/nginx/error.log
```

### Issue 4: Database Schema Changed

If you modified database tables/schema:

```bash
# Connect to PostgreSQL
sudo -u postgres psql -p 3306 -d node0db  # Adjust for each VM

# Run your schema updates
\i /path/to/schema.sql

# Or manually recreate tables
DROP TABLE IF EXISTS orders CASCADE;
CREATE TABLE orders (...);

\q

# Restart backend
sudo systemctl restart replication
```

### Issue 5: Permission Denied

```bash
# Fix ownership of web files
sudo chown -R www-data:www-data /var/www/stadvdb/

# Fix permissions
sudo chmod -R 755 /var/www/stadvdb/

# Reload Nginx
sudo systemctl reload nginx
```

---

## Verification Checklist

After updating, verify everything works:

### Backend (All VMs)

```bash
# ✅ Service is running
sudo systemctl status replication

# ✅ No errors in logs
sudo journalctl -u replication -n 50 --no-pager | grep -i error

# ✅ API responds
curl http://localhost:8000/health  # VM1
curl http://localhost:8001/health  # VM2
curl http://localhost:8002/health  # VM3

# ✅ Nodes can communicate
curl http://10.2.14.132:8000/health  # From any VM
curl http://10.2.14.133:8001/health
curl http://10.2.14.134:8002/health
```

### Frontend (VM1 Only)

```bash
# ✅ Nginx is running
sudo systemctl status nginx

# ✅ Files are served
curl http://localhost/
curl http://localhost/assets/index-*.js | head -c 100

# ✅ API proxy works
curl http://localhost/api/health

# ✅ No 404s in logs
sudo tail -n 100 /var/log/nginx/access.log | grep " 404 "
```

### From Browser

1. Open `http://ccscloud.dlsu.edu.ph:60232/`
2. Frontend loads without errors
3. Dashboard shows all nodes as "online"
4. Can create/view orders
5. No console errors in browser DevTools

---

## Quick Reference

| Task | VM(s) | Command |
|------|-------|---------|
| Update backend | All | `~/update-backend.sh` |
| Update frontend | VM1 | `~/update-frontend.sh` |
| Update both | VM1 | `~/update-all.sh` |
| View backend logs | All | `sudo journalctl -u replication -f` |
| View frontend logs | VM1 | `sudo tail -f /var/log/nginx/access.log` |
| Restart backend | All | `sudo systemctl restart replication` |
| Restart frontend | VM1 | `sudo systemctl reload nginx` |
| Test backend API | All | `curl http://localhost:800X/health` |
| Test via Nginx | VM1 | `curl http://localhost/api/health` |

**Ports:**
- VM1 (Node0): Backend `8000`, Frontend `80`
- VM2 (Node1): Backend `8001`
- VM3 (Node2): Backend `8002`

---

## Best Practices

1. **Always test locally first** before deploying to VMs
2. **Commit and push** before running updates on VMs
3. **Update VMs one at a time** to catch issues early
4. **Check logs** after each update
5. **Verify endpoints** respond correctly
6. **Keep scripts updated** if you change ports or paths
7. **Backup databases** before major schema changes

---

## Need Help?

- Backend logs: `sudo journalctl -u replication -f`
- Frontend logs: `sudo tail -f /var/log/nginx/access.log`
- Nginx errors: `sudo tail -f /var/log/nginx/error.log`
- Service status: `sudo systemctl status replication nginx`
- Test connections: Check [DEPLOYMENT.md](DEPLOYMENT.md) for more details
