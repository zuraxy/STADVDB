# STADVDB Deployment Guide

Complete guide for deploying the STADVDB distributed database system to virtual machines.

---

## Table of Contents
- [Prerequisites](#prerequisites)
- [Initial Deployment](#initial-deployment)
- [Redeployment (Updates)](#redeployment-updates)
- [Troubleshooting](#troubleshooting)
- [Quick Reference](#quick-reference)

---

## Prerequisites

### VMs Required
- **VM1 (Server0/Node1)** - Central node + Frontend + Backend
- **VM2 (Server1/Node2)** - Fragment 1 (quantity 1-5)
- **VM3 (Server2/Node3)** - Fragment 2 (quantity 6-10)

### Software Already Installed
✅ PostgreSQL 18
✅ Python 3
✅ Git

### What You Need
- VM IP addresses (e.g., 10.2.14.132, 10.2.14.133, 10.2.14.134)
- SSH access to all VMs
- GitHub repository access

---

## Initial Deployment

### Step 1: Clone Repository on VM1

```bash
# SSH into VM1 (Server0)
ssh root@ccscloud.dlsu.edu.ph -p 60532

# Clone the repository
cd ~
git clone https://github.com/zuraxy/STADVDB.git
cd STADVDB
```

---

### Step 2: Configure PostgreSQL for Remote Access

**On ALL 3 VMs (Server0, Server1, Server2):**

#### Edit pg_hba.conf
```bash
sudo nano /etc/postgresql/18/main/pg_hba.conf
```

Add at the end:
```conf
# Allow connections from VM network
host    all             all             10.2.14.0/16            trust
```

#### Edit postgresql.conf
```bash
sudo nano /etc/postgresql/18/main/postgresql.conf
```

Find and change:
```conf
listen_addresses = '*'
```

#### Restart PostgreSQL
```bash
sudo systemctl restart postgresql@18-main

# Allow firewall access
sudo ufw allow from 10.2.14.0/16 to any port 5432
```

#### Test Connectivity (from VM1)
```bash
# Test connection to VM2
psql -h 10.2.14.133 -U postgres -d node1db -c "SELECT 1;"

# Test connection to VM3
psql -h 10.2.14.134 -U postgres -d node2db -c "SELECT 1;"
```

---

### Step 3: Install Node.js on VM1

```bash
# On VM1 only
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Verify installation
node -v   # Should show v20.x.x
npm -v    # Should show 10.x.x
```

---

### Step 4: Deploy Backend on VM1

```bash
cd ~/STADVDB/backend

# Install dependencies
npm install

# Create .env file
nano .env
```

**Paste this (update IPs with your actual VM IPs):**
```env
NODE1_HOST=localhost
NODE1_PORT=5432
NODE1_USER=postgres
NODE1_PASSWORD=
NODE1_DB=node0db

NODE2_HOST=10.2.14.133
NODE2_PORT=5432
NODE2_USER=postgres
NODE2_PASSWORD=
NODE2_DB=node1db

NODE3_HOST=10.2.14.134
NODE3_PORT=5432
NODE3_USER=postgres
NODE3_PASSWORD=
NODE3_DB=node2db
```

Save: `Ctrl+X`, `Y`, `Enter`

```bash
# Install PM2 process manager
sudo npm install -g pm2

# Start backend
pm2 start index.js --name stadvdb-backend

# Save PM2 configuration
pm2 save

# Enable PM2 on system boot
pm2 startup
# Copy and run the command it outputs

# Verify backend is running
pm2 status
pm2 logs stadvdb-backend

# Test API endpoint
curl http://localhost:3000/api/test-connections
```

---

### Step 5: Deploy Frontend on VM1

```bash
cd ~/STADVDB/frontend/web-app

# Install dependencies
npm install

# Create production environment file
nano .env
```

**Paste:**
```env
VITE_API_URL=http://localhost:3000/api
```

Save: `Ctrl+X`, `Y`, `Enter`

```bash
# Build for production
npm run build

# This creates a 'dist' folder with optimized static files
```

---

### Step 6: Install and Configure Nginx on VM1

```bash
# Install Nginx
sudo apt install -y nginx

# Create web directory
sudo mkdir -p /var/www/stadvdb

# Copy built files
sudo cp -r ~/STADVDB/frontend/web-app/dist/* /var/www/stadvdb/

# Set permissions
sudo chown -R www-data:www-data /var/www/stadvdb

# Create Nginx site configuration
sudo nano /etc/nginx/sites-available/stadvdb
```

**Paste this Nginx configuration:**
```nginx
server {
    listen 80;
    server_name _;
    
    root /var/www/stadvdb;
    index index.html;

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;

    # Serve frontend files
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Proxy API requests to backend
    location /api {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # Cache static assets
    location ~* \.(jpg|jpeg|png|gif|ico|css|js|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

Save: `Ctrl+X`, `Y`, `Enter`

```bash
# Enable the site
sudo ln -s /etc/nginx/sites-available/stadvdb /etc/nginx/sites-enabled/

# Remove default site
sudo rm -f /etc/nginx/sites-enabled/default

# Test Nginx configuration
sudo nginx -t
# Should output: "syntax is ok" and "test is successful"

# Restart Nginx
sudo systemctl restart nginx

# Enable Nginx on boot
sudo systemctl enable nginx

# Verify Nginx is running
sudo systemctl status nginx
```

---

### Step 7: Access Your Application

```bash
# Get your VM1 IP address
hostname -I
```

Open a web browser and navigate to:
```
http://YOUR_VM1_IP
```

Example:
```
http://10.2.14.132
```

You should see the STADVDB dashboard with all 3 nodes showing as "online"! 🎉

---

## Redeployment (Updates)

When you make code changes and need to redeploy:

### On Your Laptop (Developer Machine)

```bash
# Navigate to project directory
cd "d:\CCS Files\STADVDB\STADVDB"

# Stage your changes
git add .

# Commit with descriptive message
git commit -m "Description of your changes"

# Push to GitHub
git push
```

---

### On VM1 (Server)

#### Update Backend

```bash
# SSH into VM1
ssh root@ccscloud.dlsu.edu.ph -p 60532

# Navigate to project
cd ~/STADVDB

# Pull latest changes
git pull

# Update backend dependencies (if package.json changed)
cd backend
npm install

# Restart backend
pm2 restart stadvdb-backend

# Check logs for errors
pm2 logs stadvdb-backend --lines 50

# Verify backend is running
curl http://localhost:3000/api/test-connections
```

#### Update Frontend

```bash
# Navigate to frontend
cd ~/STADVDB/frontend/web-app

# Update dependencies (if package.json changed)
npm install

# Rebuild
npm run build

# Copy new build to web directory
sudo cp -r dist/* /var/www/stadvdb/

# Reload Nginx (zero downtime)
sudo systemctl reload nginx

# Or restart Nginx if config changed
sudo nginx -t
sudo systemctl restart nginx
```

---

### Quick Update Script (All-in-One)

Create a deployment script for faster updates:

```bash
# Create update script
nano ~/update-stadvdb.sh
```

**Paste:**
```bash
#!/bin/bash
echo "🔄 Updating STADVDB..."

cd ~/STADVDB
echo "📥 Pulling latest changes..."
git pull

echo "🔧 Updating backend..."
cd backend
npm install
pm2 restart stadvdb-backend

echo "🎨 Rebuilding frontend..."
cd ../frontend/web-app
npm install
npm run build
sudo cp -r dist/* /var/www/stadvdb/

echo "🔄 Reloading Nginx..."
sudo systemctl reload nginx

echo "✅ Update complete!"
echo "📊 Backend status:"
pm2 status

echo "🌐 Frontend status:"
sudo systemctl status nginx --no-pager -l
```

Save and make executable:
```bash
chmod +x ~/update-stadvdb.sh
```

**To update in the future:**
```bash
~/update-stadvdb.sh
```

---

## Troubleshooting

### Backend Won't Start

```bash
# Check PM2 logs
pm2 logs stadvdb-backend

# Common issues:
# 1. Port 3000 already in use
sudo lsof -i :3000
# Kill process: sudo kill -9 <PID>

# 2. Database connection failed
# Check .env file
cat ~/STADVDB/backend/.env
# Test database connections
psql -h localhost -U postgres -d node0db
psql -h 10.2.14.133 -U postgres -d node1db
psql -h 10.2.14.134 -U postgres -d node2db

# 3. Missing .env file
cd ~/STADVDB/backend
ls -la .env
# If missing, create it (see Step 4 above)
```

---

### Frontend Shows Blank Page

```bash
# Check Nginx error logs
sudo tail -f /var/log/nginx/error.log

# Verify files exist
ls -la /var/www/stadvdb/
# Should see: index.html, assets/, etc.

# Check Nginx is serving files
curl http://localhost

# Rebuild and redeploy
cd ~/STADVDB/frontend/web-app
npm run build
sudo cp -r dist/* /var/www/stadvdb/
sudo systemctl restart nginx
```

---

### 502 Bad Gateway Error

```bash
# Backend is not running
pm2 status
pm2 restart stadvdb-backend

# Check backend logs
pm2 logs stadvdb-backend

# Verify backend is listening on port 3000
sudo netstat -tlnp | grep 3000
```

---

### Database Connection Errors

```bash
# Check PostgreSQL is running on all nodes
sudo systemctl status postgresql@18-main

# Check pg_hba.conf allows remote connections
sudo nano /etc/postgresql/18/main/pg_hba.conf
# Should have: host all all 10.2.14.0/16 trust

# Check postgresql.conf listens on all interfaces
sudo nano /etc/postgresql/18/main/postgresql.conf
# Should have: listen_addresses = '*'

# Restart PostgreSQL
sudo systemctl restart postgresql@18-main

# Test connections from VM1
psql -h 10.2.14.133 -U postgres -d node1db -c "SELECT 1;"
psql -h 10.2.14.134 -U postgres -d node2db -c "SELECT 1;"
```

---

### Node Shows "Offline" in Dashboard

```bash
# Check backend can connect to databases
cd ~/STADVDB/backend
cat .env
# Verify NODE2_HOST and NODE3_HOST IPs are correct

# Test connections manually
curl http://localhost:3000/api/test-connections

# Check PM2 logs for connection errors
pm2 logs stadvdb-backend | grep -i error
```

---

## Quick Reference

### Service Management

```bash
# Backend (PM2)
pm2 status                      # View status
pm2 logs stadvdb-backend        # View logs
pm2 restart stadvdb-backend     # Restart
pm2 stop stadvdb-backend        # Stop
pm2 start stadvdb-backend       # Start
pm2 delete stadvdb-backend      # Remove from PM2

# Frontend (Nginx)
sudo systemctl status nginx     # View status
sudo systemctl restart nginx    # Restart
sudo systemctl stop nginx       # Stop
sudo systemctl start nginx      # Start
sudo systemctl reload nginx     # Reload config (no downtime)
sudo nginx -t                   # Test configuration

# Database (PostgreSQL)
sudo systemctl status postgresql@18-main
sudo systemctl restart postgresql@18-main
sudo systemctl stop postgresql@18-main
sudo systemctl start postgresql@18-main
```

---

### File Locations

```bash
# Project
~/STADVDB/                              # Main project directory

# Backend
~/STADVDB/backend/                      # Backend source code
~/STADVDB/backend/.env                  # Backend environment variables
~/STADVDB/backend/node_modules/         # Backend dependencies

# Frontend
~/STADVDB/frontend/web-app/             # Frontend source code
~/STADVDB/frontend/web-app/dist/        # Built frontend files
/var/www/stadvdb/                       # Deployed frontend files

# Nginx
/etc/nginx/sites-available/stadvdb      # Nginx configuration
/etc/nginx/sites-enabled/stadvdb        # Enabled site symlink
/var/log/nginx/access.log               # Nginx access logs
/var/log/nginx/error.log                # Nginx error logs

# PostgreSQL
/etc/postgresql/18/main/postgresql.conf # PostgreSQL config
/etc/postgresql/18/main/pg_hba.conf     # PostgreSQL access config
/var/log/postgresql/                    # PostgreSQL logs
```

---

### Useful Commands

```bash
# Check all services
pm2 status && sudo systemctl status nginx && sudo systemctl status postgresql@18-main

# View all logs
pm2 logs stadvdb-backend
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/postgresql/postgresql-18-main.log

# Restart everything
pm2 restart stadvdb-backend
sudo systemctl restart nginx
sudo systemctl restart postgresql@18-main

# Check ports in use
sudo netstat -tlnp | grep -E '(3000|5432|80)'

# Check disk space
df -h

# Check memory usage
free -h

# Check process memory
pm2 monit
```

---

### Network Architecture

```
Internet / Browser
       ↓
   VM1 (10.2.14.132)
   ├─► Nginx :80 ──────────► React Frontend (Static Files)
   │                         /var/www/stadvdb/
   │
   └─► Nginx Proxy /api ──► Node.js Backend :3000 (PM2)
                             ~/STADVDB/backend/
                             │
                             ├─► PostgreSQL :5432 (Local - Node1)
                             │   Database: node0db
                             │   All orders (Central node)
                             │
                             ├─► VM2 (10.2.14.133) :5432 (Remote - Node2)
                             │   Database: node1db
                             │   Quantity 1-5 fragment
                             │
                             └─► VM3 (10.2.14.134) :5432 (Remote - Node3)
                                 Database: node2db
                                 Quantity 6-10 fragment
```

---

### Port Reference

| Service | Port | Description |
|---------|------|-------------|
| Nginx | 80 | Frontend web server |
| Node.js | 3000 | Backend API server |
| PostgreSQL | 5432 | Database (all 3 nodes) |

---

### Environment Variables

#### Backend (.env)
```env
NODE1_HOST=localhost        # VM1 (local)
NODE2_HOST=10.2.14.133      # VM2 IP
NODE3_HOST=10.2.14.134      # VM3 IP
NODE1_PORT=5432
NODE2_PORT=5432
NODE3_PORT=5432
NODE1_USER=postgres
NODE2_USER=postgres
NODE3_USER=postgres
NODE1_DB=node0db
NODE2_DB=node1db
NODE3_DB=node2db
```

#### Frontend (.env)
```env
VITE_API_URL=http://localhost:3000/api
```

**Note:** Frontend .env is embedded at build time. After changing it, you must rebuild:
```bash
npm run build
sudo cp -r dist/* /var/www/stadvdb/
```

---

## Security Considerations (Production)

For production deployments:

1. **Set PostgreSQL passwords**
```bash
sudo -u postgres psql
ALTER USER postgres WITH PASSWORD 'strong_password';
```

Update .env:
```env
NODE1_PASSWORD=strong_password
NODE2_PASSWORD=strong_password
NODE3_PASSWORD=strong_password
```

2. **Configure firewall properly**
```bash
sudo ufw enable
sudo ufw allow 80/tcp      # Nginx
sudo ufw allow 22/tcp      # SSH
sudo ufw allow from 10.2.14.0/16 to any port 5432  # PostgreSQL from VMs only
```

3. **Enable HTTPS with Let's Encrypt**
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

4. **Regular backups**
```bash
# Add to crontab
0 2 * * * pg_dump -U postgres node0db > /backup/node0db_$(date +\%Y\%m\%d).sql
```

---

## Monitoring

### Check Application Health

```bash
# Backend health
curl http://localhost:3000/api/test-connections

# Expected response:
# {
#   "success": true,
#   "connections": {
#     "Node1": {"status": "connected", ...},
#     "Node2": {"status": "connected", ...},
#     "Node3": {"status": "connected", ...}
#   }
# }

# Frontend health
curl http://localhost
# Should return HTML

# All services status
pm2 status && sudo systemctl is-active nginx && sudo systemctl is-active postgresql@18-main
```

### Performance Monitoring

```bash
# PM2 monitoring dashboard
pm2 monit

# System resources
htop

# Database connections
sudo -u postgres psql -c "SELECT * FROM pg_stat_activity;"

# Nginx access logs (live)
sudo tail -f /var/log/nginx/access.log
```

---

## Backup & Recovery

### Backup

```bash
# Backup script
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=/backup/$DATE

mkdir -p $BACKUP_DIR

# Backup databases
pg_dump -U postgres node0db > $BACKUP_DIR/node0db.sql

# Backup code
cp -r ~/STADVDB $BACKUP_DIR/code

# Backup Nginx config
cp /etc/nginx/sites-available/stadvdb $BACKUP_DIR/nginx.conf

# Backup PM2 config
pm2 save
cp ~/.pm2/dump.pm2 $BACKUP_DIR/pm2.dump

echo "Backup completed: $BACKUP_DIR"
```

### Recovery

```bash
# Restore database
psql -U postgres -d node0db < /backup/20251130/node0db.sql

# Restore code
rm -rf ~/STADVDB
cp -r /backup/20251130/code ~/STADVDB

# Restore configs and restart
cp /backup/20251130/nginx.conf /etc/nginx/sites-available/stadvdb
sudo nginx -t
sudo systemctl restart nginx
pm2 resurrect
```

---

## Support

For issues or questions:
1. Check logs: `pm2 logs` and `sudo tail -f /var/log/nginx/error.log`
2. Review this guide's [Troubleshooting](#troubleshooting) section
3. Verify all services are running: `pm2 status`, `sudo systemctl status nginx`
4. Test database connections from VM1 to VM2 and VM3

---

**Last Updated:** November 30, 2025
**Version:** 1.0.0
