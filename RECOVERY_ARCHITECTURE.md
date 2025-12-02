# Recovery Architecture Design Document

## Implementation Status

✅ **Implemented** - All components have been implemented and are ready for testing.

### Files Added/Modified

| File | Purpose |
|------|---------|
| `replication/recovery.py` | Core RecoveryManager class with leader/node/promotion recovery flows |
| `replication/routes/recovery.py` | REST API endpoints for recovery operations |
| `replication/tests/test_recovery.py` | Unit and integration tests |
| `replication/models.py` | Added recovery-related Pydantic models |
| `replication/crud.py` | Added snapshot export/import helpers |
| `replication/routes/admin.py` | Added demote endpoint |
| `replication/main.py` | Registered recovery manager and routes |
| `frontend/web-app/src/components/RecoveryPanel.jsx` | Recovery dashboard UI |
| `frontend/web-app/src/App.jsx` | Added Recovery tab |
| `frontend/web-app/src/services/api.js` | Added recovery API functions |

---

## Quick Start

### Starting a Leader Recovery

```bash
# Start leader recovery (Node0 catching up after downtime)
curl -X POST http://node0:8000/recovery/start \
  -H "Content-Type: application/json" \
  -d '{"mode": "leader"}'

# Response: {"job_id": "uuid-here", "status": "started"}
```

### Monitoring Recovery Progress

```bash
# Get job status
curl http://node0:8000/recovery/status/{job_id}

# Stream logs
curl http://node0:8000/recovery/logs/{job_id}?limit=100
```

### Promotion Resync (after Node1/Node2 were promoted)

```bash
curl -X POST http://node0:8000/recovery/start \
  -H "Content-Type: application/json" \
  -d '{"mode": "promotion", "since_ts": "2025-01-01T00:00:00Z", "promoted_node": "node1"}'
```

---

## Inspection Summary

The existing implementation matches assumptions:
- **Replicator** (`workers/replicator.py`): pulls `GET /oplog?since_lamport=<n>` from peers, inserts via `crud.insert_op_if_missing()`, tracks cursors in `replication_cursors` table.
- **Applier** (`workers/applier.py`): fetches unapplied ops with `FOR UPDATE SKIP LOCKED`, applies idempotently via `INSERT...ON CONFLICT`, writes `log_acknowledgements`.
- **Lamport** (`utils/lamport.py`): `next_lamport()` queries `MAX(lamport) FROM op_log WHERE origin_node=$1`.
- **GC**: Placeholder only (`gc.py`). Retention policy undefined—**must be implemented** before production recovery.

**Key gap**: No GC worker exists; assume ops may be purged externally. Recovery must handle missing ops via snapshot fallback.

---

## A. Leader Recovery (Detailed)

### A.1 State Machine

```
┌──────────┐    detect gap?    ┌───────────────┐
│  STARTUP │ ───────────────▶ │ NEEDS_REBUILD │
└──────────┘        no         └───────────────┘
      │                                │
      │ (gap ≤ threshold)              │ fetch snapshot
      ▼                                ▼
┌──────────┐   all ops applied  ┌───────────┐   ok   ┌───────┐
│ SYNCING  │ ─────────────────▶ │  GATING   │ ─────▶ │ READY │
└──────────┘                    └───────────┘        └───────┘
```

**Transitions**:
1. **STARTUP → SYNCING**: Local `max_lamport` exists; gap < GC threshold.
2. **STARTUP → NEEDS_REBUILD**: Gap exceeds threshold or local DB empty.
3. **SYNCING → GATING**: All fetched ops applied; verify counts.
4. **GATING → READY**: Enable writes after 1-second quiesce window.

### A.2 Recovery Algorithm (Step-by-Step)

```
1. Block writes (set global flag `recovery_in_progress = true`).
2. Compute local watermark:
     SELECT COALESCE(MAX(lamport), -1) AS local_max FROM op_log;
3. For each peer in [node1, node2]:
     a. GET /oplog?since_lamport={local_max}&limit=5000
     b. If HTTP 200 and ops.length > 0:
          - Insert each op via insert_op_if_missing()
          - Track max_lamport_received
     c. If HTTP error or empty for 2 retries → mark peer_unavailable
4. If any peer returns "gap_exceeded" header or local_max == -1:
     → Trigger snapshot fallback (see A.6).
5. Repeat step 3 until no new ops returned from all reachable peers.
6. Apply all unapplied ops in Lamport order (see merge algorithm A.2.1).
7. Recompute Lamport ceiling:
     UPDATE lamport_state SET ceiling = (
       SELECT MAX(lamport) FROM op_log
     ) + 1000;
8. Verify row counts match (A.4).
9. Unblock writes; transition to READY.
```

#### A.2.1 Merge Algorithm

```python
async def merge_ops(conn, ops: List[OpRecord]):
    # Dedupe by op_id (insert_op_if_missing handles ON CONFLICT)
    for op in sorted(ops, key=lambda o: (o.lamport, o.origin_node)):
        await crud.insert_op_if_missing(conn, op)
```

#### A.2.2 Cross-Partition Move Handling

When `op_type='delete'` followed by `op_type='upsert'` for same `row_id`:
- Applier processes in Lamport order; delete removes row, subsequent upsert recreates.
- Final state: single canonical row on the node matching quantity's partition.

**SQL for final row verification**:
```sql
SELECT order_id, COUNT(*) FROM orders
GROUP BY order_id HAVING COUNT(*) > 1;  -- Must return 0 rows
```

#### A.2.3 Lamport Bump After Ingest

```sql
-- After all ops ingested, bump local clock ceiling
UPDATE lamport_state 
SET ceiling = (SELECT MAX(lamport) FROM op_log) + 1000
WHERE node = 'node0';
```

If `lamport_state` table doesn't exist, add:
```sql
CREATE TABLE IF NOT EXISTS lamport_state (
  node TEXT PRIMARY KEY,
  ceiling BIGINT NOT NULL DEFAULT 0
);
```

#### A.2.4 Avoiding Replication Loops

- Recovery fetch uses **one-shot mode**: disable normal replicator during recovery.
- Fetched ops have `origin_node != 'node0'`; Node0 never re-publishes ops it didn't originate.
- After recovery, resume normal replicator; it skips already-seen ops via `ON CONFLICT DO NOTHING`.

#### A.2.5 Transaction Boundaries

- **Batch apply**: Group ops by `row_id` into micro-batches of 100; apply each batch in one transaction.
- Alternatively, apply each op in its own transaction for simpler recovery on failure.

```python
async def apply_batch(conn, ops: List[OpRecord]):
    async with conn.transaction():
        for op in ops:
            await crud.apply_op_tx(conn, op, use_transaction=False)
            await crud.insert_ack(conn, op.op_id, 'node0')
```

#### A.2.6 Write Gating Rules

- Writes allowed only when `state == READY`.
- During SYNCING/GATING: return HTTP 503 with `Retry-After: 5`.

### A.3 Pseudocode

```python
class LeaderRecovery:
    state: str = "startup"
    last_applied: int = -1
    ops_remaining: int = 0
    conflicts_detected: int = 0

    async def run(self, pool, peers: List[str]):
        self.state = "syncing"
        self.last_applied = await self._get_local_max(pool)
        
        # Check if gap exceeds threshold
        if await self._needs_snapshot(pool, peers):
            self.state = "needs_rebuild"
            await self._snapshot_reseed(pool, peers)
        
        # Incremental fetch loop
        while True:
            fetched = 0
            for peer_url in peers:
                ops = await self._fetch_ops(peer_url, self.last_applied)
                if ops:
                    await self._ingest_ops(pool, ops)
                    fetched += len(ops)
            if fetched == 0:
                break
        
        # Apply all unapplied
        await self._apply_all(pool)
        await self._bump_lamport(pool)
        
        self.state = "gating"
        await asyncio.sleep(1.0)  # quiesce window
        self.state = "ready"

    async def _fetch_ops(self, peer_url, since):
        resp = await http.get(f"{peer_url}/oplog", params={"since_lamport": since})
        return [OpRecord(**o) for o in resp.json()]

    async def _ingest_ops(self, pool, ops):
        async with pool.acquire() as conn:
            for op in sorted(ops, key=lambda o: (o.lamport, o.origin_node)):
                inserted = await crud.insert_op_if_missing(conn, op)
                if inserted:
                    self.ops_remaining += 1
                self.last_applied = max(self.last_applied, op.lamport)
```

### A.4 Progress Checkpoints / Metrics

| Metric | Description |
|--------|-------------|
| `last_applied_lamport` | Highest Lamport ingested |
| `ops_remaining` | Count of `applied=false` ops |
| `ops_ingested` | Total ops fetched this session |
| `conflicts_detected` | Rows with duplicate order_id (should be 0) |
| `recovery_state` | startup/syncing/needs_rebuild/gating/ready |

### A.5 Conflict Policy

- **Last-Lamport-Wins**: Higher lamport wins; tie-breaker: `origin_node ASC` (node0 < node1 < node2).
- **Manual review**: Flag if same `order_id` has ops from multiple origins within 1-second window:

```sql
INSERT INTO recovery_conflicts (order_id, ops, flagged_at)
SELECT row_id, array_agg(op_id), NOW()
FROM op_log
WHERE row_id IN (SELECT row_id FROM op_log GROUP BY row_id HAVING COUNT(DISTINCT origin_node) > 1)
GROUP BY row_id;
```

### A.6 GC/Retention & Snapshot Fallback

**Retention Policy**: Keep ops for 24 hours or until acknowledged by all 3 nodes.

**Threshold**: If `peer_max_lamport - local_max > 10000`, trigger snapshot.

**Snapshot Flow**:
```
1. POST /recovery/request_snapshot to peer → returns job_id
2. GET /recovery/snapshot/{job_id} → CSV stream of orders table
3. TRUNCATE orders; COPY orders FROM STDIN;
4. Reset local lamport cursor to peer's max_lamport
5. Resume incremental sync
```

---

## B. Node Recovery (Concise)

**On cold rejoin (Node1 or Node2)**:

```python
async def node_recovery(pool, peers):
    local_max = await get_max_lamport(pool)
    
    for peer in peers:
        ops = await fetch_ops_since(peer, local_max)
        if "gap_exceeded" in response.headers:
            await request_snapshot(peer, partition=self.partition)
            return
        for op in ops:
            await crud.insert_op_if_missing(pool, op)
    
    # Resume applier; it will apply in Lamport order
    applier.start()
```

**Endpoints called**:
- `GET /oplog?since_lamport={local_max}`
- `POST /recovery/request_snapshot` (if gap > threshold)

---

## C. Replica Promotion Recovery (Concise)

**When Node0 returns after Node1/Node2 were promoted**:

```
1. Node1/Node2 record promotion_time in metadata table at promotion:
   INSERT INTO promotion_log (node, promoted_at, demoted_at)
   VALUES ('node1', NOW(), NULL);

2. When Node0 requests recovery, promoted nodes filter ops:
   GET /oplog?since_lamport=-1&since_ts={promotion_time}&until_ts={now}

3. Node0 ingests promotion-era ops using standard merge logic.

4. Node0 broadcasts demotion:
   POST /admin/demote to Node1, Node2
   → Nodes set promoted=false, update promotion_log.demoted_at

5. Promoted nodes stop accepting partition writes; resume as replicas.
```

**Atomic promotion_time recording**:
```sql
BEGIN;
UPDATE node_state SET promoted = true, promotion_ts = NOW() WHERE node = $1;
COMMIT;
```

---

## D. Recovery API Surface

| Endpoint | Method | Request | Response |
|----------|--------|---------|----------|
| `/recovery/start` | POST | `{mode: "leader"\|"node"\|"promotion", since_ts?}` | `{job_id, state}` |
| `/recovery/status/{job_id}` | GET | — | `{state, last_applied_lamport, ops_remaining, conflicts}` |
| `/recovery/logs/{job_id}` | GET | `?format=json\|text` | Recovery log entries |
| `/recovery/force_snapshot` | POST | `{peer, partition?}` | `{job_id}` |
| `/recovery/request_snapshot` | POST | `{partition?}` | `{job_id, stream_url}` |
| `/recovery/snapshot/{job_id}` | GET | — | CSV stream |

---

## E. Minimal Recovery UI (Wireframe Behavior)

**Admin Panel → Recovery Tab**:

```
┌─────────────────────────────────────────────────────────┐
│  RECOVERY DASHBOARD                                     │
├─────────────────────────────────────────────────────────┤
│  Node Health:  [node0: READY ✓] [node1: OK] [node2: OK] │
│                                                         │
│  Last Applied Lamport: 45,231                           │
│  Ops Outstanding:      0                                │
│  Conflicts Detected:   0                                │
│                                                         │
│  [Start Reconverge] [Force Snapshot] [Download Logs]    │
│                                                         │
│  ⚠️  Writes blocked during final reconciliation          │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │ Live Log:                                       │    │
│  │ 12:01:05 Fetching from node1... 523 ops        │    │
│  │ 12:01:06 Fetching from node2... 412 ops        │    │
│  │ 12:01:08 Applying batch 1/10...                │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

**UX Rules**:
- Show warning banner when writes are gated.
- Disable "Start Reconverge" if recovery already in progress.
- Poll `/recovery/status/{job_id}` every 2s for live updates.

---

## F. Tests & Verification Plan

| Scenario | Steps | Assertions |
|----------|-------|------------|
| **Leader Recovery** | Stop Node0; write 100 orders on Node1, 100 on Node2; restart Node0; run recovery | Node0 has 200 orders; no duplicate order_id; values match last-lamport-wins |
| **GC Gap Fallback** | Simulate GC on peers (delete old ops); restart Node0 | Snapshot fallback triggers; final state matches peers |
| **Idempotency** | Replay same ops twice | Final row count unchanged; no errors |
| **Cross-Partition Move** | Create order qty=3 on Node1; update to qty=10; run replication | Order exists only on Node2 with qty=10 |
| **Promotion Recovery** | Promote Node1; write 50 orders; restore Node0; run promotion recovery | Node0 has all 50 orders; Node1 demoted |

---

## G. Integration Checklist

| Function | Module | Signature | Status |
|----------|--------|-----------|--------|
| `fetch_ops_since(conn, lamport, origin_node?, limit)` | `crud` | Returns `List[OpRecord]` | ✅ Exists |
| `insert_op_if_missing(conn, op)` | `crud` | Returns `bool` | ✅ Exists |
| `apply_op_tx(conn, op, use_transaction)` | `crud` | Idempotent upsert/delete | ✅ Exists |
| `insert_ack(conn, op_id, node)` | `crud` | Writes acknowledgement | ✅ Exists |
| `upsert_replication_cursor(conn, node, lamport)` | `crud` | Updates cursor | ✅ Exists |
| `load_replication_cursors(conn)` | `crud` | Returns `Dict[str,int]` | ✅ Exists |
| `export_orders_snapshot(conn, partition?, partition_rule)` | `crud` | Returns `List[Dict]` | ✅ **Implemented** |
| `import_orders_snapshot(conn, data)` | `crud` | Returns `int` (imported count) | ✅ **Implemented** |
| `get_max_lamport(conn)` | `crud` | Returns `int` | ✅ **Implemented** |
| `export_snapshot(partition, format)` | `recovery` | Returns snapshot dict | ✅ **Implemented** |
| `import_snapshot_helper(pool, data)` | `recovery` | Imports snapshot data | ✅ **Implemented** |
| `set_recovery_flag(flag)` | `recovery` | Gates writes globally | ✅ **Implemented** |
| `get_recovery_flag()` | `recovery` | Returns current flag | ✅ **Implemented** |

---

## H. Implementation Roadmap

| PR | Scope | Deliverables | Status |
|----|-------|--------------|--------|
| **1** | Job scaffolding | `RecoveryManager` class, state machine, `/recovery/*` endpoints, status/logs API | ✅ Complete |
| **2** | Fetch/merge engine | Incremental op fetch loop, dedup, Lamport ordering, cursor updates | ✅ Complete |
| **3** | Apply engine | Batch apply with idempotent upserts, ack writes, conflict detection | ✅ Complete |
| **4** | GC-gap snapshot | `/recovery/snapshot` endpoint, CSV/JSON export/import, fallback trigger logic | ✅ Complete |
| **5** | Promotion resync | Promotion metadata table, filtered fetch by `since_ts`, demotion broadcast | ✅ Complete |
| **6** | UI wiring | Admin panel recovery tab, live log polling, gating warnings | ✅ Complete |
| **7** | Tests/chaos | pytest scenarios for all cases in Section F, mock infrastructure | ✅ Complete |

---

## Running Tests

```bash
# Run recovery tests
cd replication
pytest tests/test_recovery.py -v

# Run with coverage
pytest tests/test_recovery.py -v --cov=replication.recovery
```

## Running Multiple Instances (Development)

```bash
# Terminal 1: Node0 (Master)
DATABASE_DSN=postgres://user:pass@localhost:5432/node0 \
NODE_NAME=node0 \
PEER_NODES='node1=http://localhost:8001,node2=http://localhost:8002' \
uvicorn replication.main:app --port 8000

# Terminal 2: Node1
DATABASE_DSN=postgres://user:pass@localhost:5433/node1 \
NODE_NAME=node1 \
PEER_NODES='node0=http://localhost:8000,node2=http://localhost:8002' \
uvicorn replication.main:app --port 8001

# Terminal 3: Node2
DATABASE_DSN=postgres://user:pass@localhost:5434/node2 \
NODE_NAME=node2 \
PEER_NODES='node0=http://localhost:8000,node1=http://localhost:8001' \
uvicorn replication.main:app --port 8002
```

---

*Document version: 2.0 | Implementation complete*
