# 🚀 Getting Started - Quick Instructions

## You have everything installed! Just follow these 3 simple steps:

### Step 1: Run Setup (ONE TIME ONLY)

```powershell
.\setup.ps1
```

This will:
- Create 3 PostgreSQL databases (node0db, node1db, node2db)
- Initialize all database tables and constraints
- Install frontend dependencies
- Configure environment files

**You'll be asked for your PostgreSQL password** - this is the password you set when installing PostgreSQL.

---

### Step 2: Start Backend Nodes

Open a new PowerShell terminal and run:

```powershell
.\start-nodes.ps1
```

This opens 3 windows running:
- **Node 0** (Central node) on port 8000
- **Node 1** (Quantity 1-5) on port 8001
- **Node 2** (Quantity 6-10) on port 8002

---

### Step 3: Start Frontend

Open another PowerShell terminal and run:

```powershell
.\start-frontend.ps1
```

This starts the React web interface on port 5173.

---

### Step 4: Access the Application

Open your browser to: **http://localhost:5173**

You can also access the API documentation:
- Node 0: http://localhost:8000/docs
- Node 1: http://localhost:8001/docs
- Node 2: http://localhost:8002/docs

---

## Troubleshooting

### "Cannot be loaded because running scripts is disabled"

Run this in PowerShell (as Administrator):
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### "Port already in use"

Find and kill the process:
```powershell
# Find process on port 8000
Get-NetTCPConnection -LocalPort 8000 | Select-Object OwningProcess

# Kill it (replace <PID> with the process ID)
Stop-Process -Id <PID> -Force
```

### "Connection refused" or "Can't connect to database"

1. Check PostgreSQL is running:
   ```powershell
   Get-Service postgresql*
   ```

2. Start it if stopped:
   ```powershell
   Start-Service postgresql*
   ```

3. Verify your password is correct

---

## Testing the System

Once everything is running, try these in the web interface:

1. **Create Order**: Add new orders and watch them replicate
2. **Concurrency Test**: Run Case 1, 2, 3 scenarios
3. **View Replication Status**: Check how nodes are syncing

---

## Stopping the System

- Close each terminal window running the nodes
- Or press `Ctrl+C` in each window
- Frontend: Press `Ctrl+C` in the terminal running `npm run dev`

---

## Need More Help?

- See `LOCAL_SETUP_GUIDE.md` for detailed documentation
- See `QUICKSTART.md` for manual setup instructions
- Check API documentation at http://localhost:8000/docs

---

**Pro Tip**: Keep the terminal windows open while developing - they'll auto-reload when you make code changes! 🎉
