# Recovery Subsystem Documentation

## Overview

The Recovery Subsystem is a critical component of the distributed database demo that handles node recovery scenarios. It ensures data consistency and availability when nodes fail and need to rejoin the cluster.

This documentation covers the complete implementation of the Recovery Subsystem, including:
- **Core Recovery Manager** - The state machine and recovery logic
- **Recovery APIs** - FastAPI endpoints for recovery operations
- **Recovery Dashboard** - HTML/JS UI for monitoring and controlling recovery

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [State Machine](#state-machine)
3. [Recovery Modes](#recovery-modes)
4. [Implementation Details](#implementation-details)
5. [API Reference](#api-reference)
6. [Dashboard Guide](#dashboard-guide)
7. [Algorithm Deep Dive](#algorithm-deep-dive)
8. [Configuration](#configuration)
9. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

### System Context

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Distributed Database Cluster                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐           │
│   │    Node0     │     │    Node1     │     │    Node2     │           │
│   │   (Leader)   │◄───►│   (Replica)  │◄───►│   (Replica)  │           │
│   │              │     │  qty <= 5    │     │  qty > 5     │           │
│   └──────┬───────┘     └──────────────┘     └──────────────┘           │
│          │                                                               │
│          │  Recovery                                                     │
│          ▼                                                               │
│   ┌──────────────────────────────────────────────────────────────────┐  │
│   │                    Recovery Subsystem                             │  │
│   │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐   │  │
│   │  │ RecoveryManager │  │  Recovery APIs  │  │   Dashboard     │   │  │
│   │  │  (State Machine)│  │  (FastAPI)      │  │   (HTML/JS)     │   │  │
│   │  └─────────────────┘  └─────────────────┘  └─────────────────┘   │  │
│   └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Components

| Component | File | Description |
|-----------|------|-------------|
| RecoveryManager | `workers/recovery_manager.py` | Core state machine and recovery logic |
| Recovery Router | `routes/recovery.py` | FastAPI endpoints and embedded dashboard |
| Static Dashboard | `static/recovery_dashboard.html` | Standalone HTML dashboard |

### Database Tables Used

The recovery subsystem interacts with these existing tables:

```sql
-- Operations log (source of truth for replication)
CREATE TABLE op_log (
    op_id UUID PRIMARY KEY,
    origin_node TEXT NOT NULL,
    op_type TEXT NOT NULL,        -- 'upsert' or 'delete'
    table_name TEXT NOT NULL,
    row_id UUID NOT NULL,
    payload JSONB,
    ts TIMESTAMP WITH TIME ZONE,
    lamport BIGINT NOT NULL,
    applied BOOLEAN DEFAULT FALSE,
    applied_ts TIMESTAMP WITH TIME ZONE
);

-- Orders table (the actual data)
CREATE TABLE orders (
    order_id UUID PRIMARY KEY,
    quantity INTEGER NOT NULL,
    payload JSONB,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Replication cursors (tracks sync progress)
CREATE TABLE replication_cursors (
    node TEXT PRIMARY KEY,
    last_lamport BIGINT NOT NULL
);
```

---

## State Machine

The Recovery Manager implements a state machine with the following states:

```
                 ┌─────────────────────────────────────────┐
                 │                                         │
                 ▼                                         │
┌─────────┐   ┌──────────────┐   ┌─────────┐   ┌───────┐ │
│ STARTUP │──►│ NEEDS_REBUILD│──►│ SYNCING │──►│ READY │ │
└─────────┘   └──────────────┘   └─────────┘   └───────┘ │
     │               │                │             │      │
     │               │                │             │      │
     │               ▼                ▼             │      │
     │         ┌──────────────────────────────┐   │      │
     └────────►│           FAILED             │◄──┘      │
               └──────────────────────────────┘          │
                              │                           │
                              └───────────────────────────┘
                              (Retry Recovery)
```

### State Descriptions

| State | Description | Actions |
|-------|-------------|---------|
| `STARTUP` | Initial state on node boot | Check local lamport, count unapplied ops |
| `NEEDS_REBUILD` | Node is behind peers | Prepare for sync operation |
| `SYNCING` | Actively fetching and applying ops | Reject writes, allow reads |
| `READY` | Node is caught up and operational | Resume normal operations |
| `FAILED` | Recovery failed | Manual intervention may be required |

---

## Recovery Modes

### Leader Recovery (Node0)

**Scenario:** Node0 (the leader/master) crashes and restarts. While it was down, replicas may have continued operating (especially if promoted).

**Flow:**
1. Node0 starts and enters `STARTUP`
2. Checks its `max(lamport)` in `op_log`
3. Queries Node1 and Node2 for ops with `lamport > local_max`
4. If peers have newer ops → enters `NEEDS_REBUILD`
5. Fetches all missing ops via `GET /oplog?since_lamport=X`
6. Deduplicates ops by `op_id`
7. Sorts ops by `(lamport, origin_node)` for deterministic replay
8. Applies ops using Last-Writer-Wins conflict resolution
9. Enters `READY` when caught up

### Replica Promotion Recovery

**Scenario:** While Node0 was down, Node1 or Node2 was promoted and accepted writes. When Node0 recovers, it must sync these new ops.

**Flow:**
1. Same as Leader Recovery
2. Special handling for partition moves:
   - If an order's `quantity` changed such that it belongs to a different partition
   - Delete from old partition, insert into new partition
3. Explicit merge with conflict resolution

---

## Implementation Details

### RecoveryManager Class

```python
class RecoveryManager:
    """Core recovery engine implementing the state machine."""
    
    def __init__(self, pool, settings, http_client, applier_trigger):
        self.pool = pool                    # asyncpg connection pool
        self.settings = settings            # Application settings
        self.http_client = http_client      # HTTP client for peer communication
        self.applier_trigger = applier_trigger  # Callback to trigger applier
        
        self._state = RecoveryState.STARTUP
        self._jobs = {}                     # Active/completed recovery jobs
        self._current_job_id = None
        self._lock = asyncio.Lock()         # Prevent concurrent recovery
```

### Recovery Steps

#### Step A: Check Local State
```python
async def _step_a_check_local_state(self, job_id):
    """Check last_applied_lamport to determine local state."""
    async with self.pool.acquire() as conn:
        max_lamport = await conn.fetchval(
            "SELECT COALESCE(MAX(lamport), 0) FROM op_log"
        )
        unapplied = await conn.fetchval(
            "SELECT COUNT(*) FROM op_log WHERE applied = false"
        )
```

#### Step B: Check Rebuild Needed
```python
async def _step_b_check_rebuild_needed(self, job_id):
    """Check if rebuild is needed by comparing with peers."""
    for peer in self.settings.peer_nodes:
        payload = await self.http_client.get_json(
            f"{peer.base_url}/oplog",
            params={"since_lamport": local_max, "limit": 1},
        )
        # If any peer has newer ops, we need to rebuild
```

#### Step C: Fetch and Merge Ops
```python
async def _step_c_fetch_and_merge(self, job_id):
    """Fetch missing ops from peers and merge them."""
    all_ops = {}  # Dict[UUID, OpRecord] for deduplication
    
    for peer in self.settings.peer_nodes:
        peer_ops = await self._fetch_ops_from_peer(peer, since_lamport)
        
        for op in peer_ops:
            if op.op_id not in all_ops:
                all_ops[op.op_id] = op
            else:
                # Last-Writer-Wins: higher lamport wins
                if op.lamport > all_ops[op.op_id].lamport:
                    all_ops[op.op_id] = op
    
    # Sort by (lamport, origin_node) for deterministic replay
    return sorted(all_ops.values(), key=lambda op: (op.lamport, op.origin_node))
```

#### Step D: Apply Ops
```python
async def _step_d_apply_ops(self, job_id, ops):
    """Apply ops with partition move handling and conflict resolution."""
    for op in ops:
        # Insert into local op_log
        await self._insert_op_if_missing(conn, op)
        
        if op.op_type == "delete":
            await conn.execute("DELETE FROM orders WHERE order_id = $1", op.row_id)
        else:
            # Check partition ownership for replicas
            if self.settings.node_name != self.settings.default_master:
                target_node = target_node_for_quantity(quantity, threshold)
                if target_node != self.settings.node_name.lower():
                    # Partition move - delete local copy
                    await conn.execute("DELETE FROM orders WHERE order_id = $1", op.row_id)
                    continue
            
            # Apply upsert with ON CONFLICT
            await conn.execute("""
                INSERT INTO orders (order_id, quantity, payload, created_at, updated_at)
                VALUES ($1, $2, $3::jsonb, $4, $4)
                ON CONFLICT (order_id)
                DO UPDATE SET quantity = EXCLUDED.quantity, ...
            """, ...)
        
        # Mark as applied
        await conn.execute(
            "UPDATE op_log SET applied = true, applied_ts = $2 WHERE op_id = $1",
            op.op_id, datetime.now(timezone.utc)
        )
```

#### Step E: Finalize
```python
async def _step_e_finalize(self, job_id):
    """Finalize recovery and transition to READY state."""
    # Update replication cursors
    for peer in self.settings.peer_nodes:
        await conn.execute("""
            INSERT INTO replication_cursors (node, last_lamport)
            VALUES ($1, $2)
            ON CONFLICT (node) DO UPDATE SET last_lamport = EXCLUDED.last_lamport
        """, peer.name, final_lamport)
    
    # Trigger applier for any remaining ops
    if self.applier_trigger:
        await self.applier_trigger()
    
    # Transition to READY
    self._state = RecoveryState.READY
```

### Conflict Resolution: Last-Writer-Wins (LWW)

```python
def resolve_conflict(existing_op, new_op):
    """
    Last-Writer-Wins conflict resolution.
    
    1. Higher Lamport timestamp wins
    2. On tie: lexicographically higher origin_node wins
    """
    if new_op.lamport > existing_op.lamport:
        return new_op
    elif new_op.lamport == existing_op.lamport:
        if new_op.origin_node > existing_op.origin_node:
            return new_op
    return existing_op
```

---

## API Reference

### Start Recovery

```http
POST /recovery/start
Content-Type: application/json

{
    "mode": "leader"  // or "node"
}
```

**Response:**
```json
{
    "job_id": "abc12345",
    "mode": "leader",
    "message": "Recovery started in leader mode"
}
```

### Get Recovery Status

```http
GET /recovery/status/{job_id}
```

**Response:**
```json
{
    "job_id": "abc12345",
    "is_running": true,
    "progress": {
        "state": "syncing",
        "mode": "leader",
        "ops_fetched": 150,
        "ops_merged": 145,
        "ops_applied": 100,
        "ops_remaining": 45,
        "ops_skipped": 5,
        "ops_conflicted": 3,
        "peers_contacted": 2,
        "peers_failed": 0,
        "start_time": "2024-01-15T10:30:00Z",
        "end_time": null,
        "last_error": null,
        "local_lamport_start": 500,
        "local_lamport_end": 645
    }
}
```

### Stream Recovery Logs

```http
GET /recovery/logs/{job_id}?stream=true
```

**Response:** Server-Sent Events (SSE) stream
```
data: [2024-01-15T10:30:00Z] Recovery job started: mode=leader
data: [2024-01-15T10:30:01Z] Step A: Checking local state...
data: [2024-01-15T10:30:02Z] Local state: max_lamport=500, unapplied_ops=0
...
```

### Get Node Health

```http
GET /recovery/health
```

**Response:**
```json
{
    "node": "node0",
    "state": "ready",
    "is_ready": true,
    "local_stats": {
        "max_lamport": 645,
        "total_ops": 500,
        "unapplied_ops": 0,
        "total_orders": 250
    },
    "peers": [
        {
            "name": "node1",
            "url": "http://localhost:8001",
            "status": "healthy",
            "promoted": false
        },
        {
            "name": "node2",
            "url": "http://localhost:8002",
            "status": "healthy",
            "promoted": false
        }
    ]
}
```

### Get Sync Gap

```http
GET /recovery/gap
```

**Response:**
```json
{
    "local_max_lamport": 500,
    "gaps": {
        "gap_node1": 45,
        "gap_node2": 30
    }
}
```

### Force Snapshot

```http
POST /recovery/snapshot
```

**Response:**
```json
{
    "job_id": "def67890",
    "message": "Snapshot/resync initiated"
}
```

### List All Jobs

```http
GET /recovery/jobs
```

**Response:**
```json
{
    "jobs": [
        {
            "job_id": "abc12345",
            "mode": "leader",
            "state": "ready",
            "is_running": false,
            "start_time": "2024-01-15T10:30:00Z",
            "end_time": "2024-01-15T10:31:00Z"
        }
    ]
}
```

### Get Current State

```http
GET /recovery/state
```

**Response:**
```json
{
    "state": "ready",
    "is_ready": true,
    "is_syncing": false,
    "node": "node0"
}
```

### Recovery Dashboard

```http
GET /recovery/dashboard
```

Returns the HTML dashboard page for browser viewing.

---

## Dashboard Guide

### Accessing the Dashboard

1. **Embedded Dashboard:** Navigate to `http://<node-address>:8000/recovery/dashboard`
2. **Standalone Dashboard:** Open `static/recovery_dashboard.html` in a browser and configure the API URL

### Dashboard Features

#### Node Health Panel
- Shows status of all nodes (this node + peers)
- Green indicator: Healthy
- Yellow indicator: Syncing
- Red indicator: Unreachable

#### Current State Panel
- Displays the current recovery state badge
- Shows local statistics:
  - Max Lamport timestamp
  - Total operations in op_log
  - Unapplied operations count
  - Total orders count

#### Sync Gap Panel
- Shows how many ops behind this node is
- `0` = synced
- `+N` = N ops behind
- `N/A` = peer unreachable

#### Recovery Controls
- **Mode Selection:** Choose Leader or Node recovery mode
- **Start Recovery:** Begins a new recovery job
- **Force Snapshot:** Triggers a full resync from peers

#### Progress Panel (appears during recovery)
- Progress bar showing completion percentage
- Metrics: ops fetched, merged, conflicted, skipped

#### Logs Panel
- Real-time log stream via SSE
- Color-coded entries:
  - Green: Success messages
  - Yellow: Warnings
  - Red: Errors

---

## Algorithm Deep Dive

### Lamport Clock Ordering

The system uses Lamport timestamps for total ordering:

```
┌────────────────────────────────────────────────────────────────┐
│                    Lamport Clock Rules                          │
├────────────────────────────────────────────────────────────────┤
│ 1. Before sending a message, increment the clock              │
│ 2. Upon receiving, set clock = max(local, received) + 1       │
│ 3. For conflict resolution: (lamport, origin_node) tuple      │
└────────────────────────────────────────────────────────────────┘
```

### Operation Deduplication

```python
# During merge, ops are deduped by op_id (UUID)
all_ops = {}  # Dict[UUID, OpRecord]

for op in peer_ops:
    if op.op_id not in all_ops:
        all_ops[op.op_id] = op
    else:
        # Conflict - same op from different sources
        # Use LWW to pick winner
        winner = lww_resolve(all_ops[op.op_id], op)
        all_ops[op.op_id] = winner
```

### Partition Move Handling

When `quantity` changes and crosses the partition boundary:

```python
# Partition rule: quantity <= threshold → node1, else → node2

def handle_partition_move(op, current_node, threshold):
    quantity = op.payload.get("quantity")
    target = "node1" if quantity <= threshold else "node2"
    
    if target != current_node:
        # This row has moved to another partition
        # Delete local copy - the target node will have it
        DELETE FROM orders WHERE order_id = op.row_id
```

### Idempotent Operations

All database operations use `ON CONFLICT` clauses for idempotency:

```sql
-- Insert op_log entry (idempotent)
INSERT INTO op_log (...) VALUES (...)
ON CONFLICT (op_id) DO NOTHING;

-- Upsert order (idempotent)
INSERT INTO orders (order_id, quantity, payload, created_at, updated_at)
VALUES ($1, $2, $3::jsonb, $4, $4)
ON CONFLICT (order_id)
DO UPDATE SET 
    quantity = EXCLUDED.quantity,
    payload = EXCLUDED.payload,
    updated_at = EXCLUDED.updated_at;
```

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_DSN` | PostgreSQL connection string | Required |
| `NODE_NAME` | This node's identifier | `node0` |
| `PEER_NODES` | JSON or comma-separated peer URLs | `[]` |
| `POLL_INTERVAL` | Replicator poll interval (seconds) | `5` |
| `DEFAULT_MASTER` | Default leader node name | `node0` |
| `PARTITION_RULE` | Quantity threshold for partitioning | `5` |

### Example Configuration

```bash
# Node0 (Leader)
export DATABASE_DSN="postgresql://user:pass@localhost:5432/db0"
export NODE_NAME="node0"
export PEER_NODES="node1=http://localhost:8001,node2=http://localhost:8002"

# Node1 (Replica, qty <= 5)
export DATABASE_DSN="postgresql://user:pass@localhost:5433/db1"
export NODE_NAME="node1"
export PEER_NODES="node0=http://localhost:8000,node2=http://localhost:8002"
```

---

## Troubleshooting

### Common Issues

#### Recovery Stuck in SYNCING

**Symptoms:** Progress bar not moving, state remains `SYNCING`

**Solutions:**
1. Check peer connectivity: `GET /recovery/health`
2. Verify peers are responding: `curl http://peer:port/`
3. Check for large op_log backlogs
4. Review logs for specific errors

#### High Conflict Count

**Symptoms:** `ops_conflicted` metric is unexpectedly high

**Causes:**
- Multiple nodes writing same rows during network partition
- Clock drift between nodes

**Solutions:**
1. This is expected during split-brain recovery
2. LWW ensures eventual consistency
3. Review application logic to minimize conflicts

#### Peer Unreachable

**Symptoms:** `peers_failed > 0` in recovery status

**Solutions:**
1. Verify network connectivity
2. Check firewall rules
3. Ensure peer nodes are running
4. Recovery will proceed with available peers

#### FAILED State

**Symptoms:** Recovery ends in `FAILED` state

**Solutions:**
1. Check `last_error` in status response
2. Review recovery logs
3. Fix underlying issue
4. Restart recovery with `POST /recovery/start`

### Debugging Commands

```bash
# Check local op_log status
psql -c "SELECT COUNT(*), MAX(lamport), SUM(CASE WHEN applied THEN 1 ELSE 0 END) FROM op_log;"

# Find unapplied ops
psql -c "SELECT * FROM op_log WHERE applied = false ORDER BY lamport LIMIT 10;"

# Check replication cursors
psql -c "SELECT * FROM replication_cursors;"

# Manual peer check
curl http://localhost:8001/oplog?since_lamport=0&limit=5 | jq .
```

---

## File Structure

```
replication/
├── main.py                      # Updated to include recovery router
├── routes/
│   ├── __init__.py              # Updated exports
│   └── recovery.py              # Recovery API router (NEW)
├── workers/
│   ├── __init__.py              # Updated exports
│   └── recovery_manager.py      # Core recovery logic (NEW)
└── static/
    └── recovery_dashboard.html  # Standalone dashboard (NEW)
```

---

## Integration with Existing System

### Changes to main.py

1. Import recovery router and RecoveryManager
2. Include recovery router in app
3. Initialize RecoveryManager on startup
4. Wire applier trigger callback

### How Recovery Interacts with Existing Components

```
┌──────────────────────────────────────────────────────────────┐
│                     Recovery Flow                             │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────┐                                             │
│  │ HTTP Client │◄───── Fetch ops from peers (/oplog)         │
│  └─────────────┘                                             │
│         │                                                     │
│         ▼                                                     │
│  ┌─────────────────┐                                         │
│  │ RecoveryManager │                                         │
│  │                 │──── Insert ops to local op_log          │
│  │                 │──── Apply ops to orders table           │
│  └─────────────────┘                                         │
│         │                                                     │
│         ▼                                                     │
│  ┌─────────────────┐                                         │
│  │ ApplierWorker   │◄───── Triggered after recovery          │
│  │                 │       for remaining ops                  │
│  └─────────────────┘                                         │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## Testing the Recovery Subsystem

### Manual Testing Steps

1. **Start all nodes normally**
   ```bash
   # Terminal 1 - Node0
   cd replication && uvicorn main:app --port 8000
   
   # Terminal 2 - Node1
   cd replication && NODE_NAME=node1 uvicorn main:app --port 8001
   
   # Terminal 3 - Node2
   cd replication && NODE_NAME=node2 uvicorn main:app --port 8002
   ```

2. **Create some orders via Node0**
   ```bash
   curl -X POST http://localhost:8000/orders \
     -H "Content-Type: application/json" \
     -d '{"quantity": 3, "payload": {"item": "test"}}'
   ```

3. **Stop Node0 to simulate failure**
   ```bash
   # Ctrl+C on Terminal 1
   ```

4. **Create orders on Node1 (promote if needed)**
   ```bash
   curl -X POST http://localhost:8001/admin/promote -d '{"promote": true}'
   curl -X POST http://localhost:8001/orders \
     -H "Content-Type: application/json" \
     -d '{"quantity": 2}'
   ```

5. **Restart Node0 and trigger recovery**
   ```bash
   # Terminal 1
   uvicorn main:app --port 8000
   
   # Trigger recovery
   curl -X POST http://localhost:8000/recovery/start \
     -H "Content-Type: application/json" \
     -d '{"mode": "leader"}'
   ```

6. **Monitor recovery via dashboard**
   - Open `http://localhost:8000/recovery/dashboard`
   - Watch progress and logs

---

## Summary

The Recovery Subsystem provides a robust mechanism for handling node failures in the distributed database demo. Key features:

- **State Machine Architecture:** Clean, predictable state transitions
- **Pull-Based Sync:** Uses existing `/oplog` endpoint for fetching ops
- **Last-Writer-Wins:** Deterministic conflict resolution using Lamport clocks
- **Idempotent Operations:** Safe to retry without data corruption
- **Partition Awareness:** Handles partition moves correctly
- **Real-time Monitoring:** Dashboard with live progress and logs
- **API-Driven:** All operations controllable via REST API

The implementation follows the constraints of no external message queues, using only database tables and HTTP polling for coordination.
