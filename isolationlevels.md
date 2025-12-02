
## Transaction Orchestrator (Concurrency Harness)

The FastAPI service now exposes a **parameterized** transaction orchestrator that launches real `BEGIN … SELECT … pg_sleep … UPDATE … COMMIT` scripts against any pair of nodes. Use it to demonstrate isolation anomalies directly from the React UI (Concurrency tab → "Transaction Orchestrator") or by calling the REST endpoints below.

### REST endpoints

- `POST /orchestrator/run` — body accepts:
  - `scenario`: `read_read`, `read_write`, or `write_write`.
  - `isolation_level`: `READ_UNCOMMITTED`, `READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE`.
  - `parallel_clients`: 2–16 (writer counts toward the total).
  - `order_id` (optional UUID) — blank values auto-provision a fresh order.
  - `node_x` / `node_y`: logical node labels (`node0`/`node1`/`node2`).
  - `new_value_1` & `new_value_2`: writer target quantity (read-write) or increments (write-write).
  Returns `{ "run_id": "...", "status": "started" }`.
- `GET /orchestrator/status/{run_id}` — run metadata, per-client step logs, and a verdict with per-node snapshots.
- `GET /orchestrator/stream/{run_id}` — Server-Sent Events (SSE) stream emitting every log entry in real time (UI uses this for the live feed). `GET /orchestrator/logs/{run_id}` remains available for polling fallbacks.
- `POST /orchestrator/abort/{run_id}` — cancels an in-flight run and rolls back open transactions.

> ℹ️ PostgreSQL folds `READ_UNCOMMITTED` into `READ COMMITTED`; the orchestrator surfaces this note (and the frontend shows a shield banner) so readers understand why dirty reads cannot be demonstrated directly.

#### Sample payloads

```json
{
  "scenario": "read_write",
  "isolation_level": "READ_COMMITTED",
  "parallel_clients": 3,
  "node_x": "node0",
  "node_y": "node1",
  "new_value_1": 42
}
```

```json
{
  "scenario": "write_write",
  "isolation_level": "SERIALIZABLE",
  "parallel_clients": 2,
  "node_x": "node0",
  "node_y": "node2",
  "new_value_1": 1,
  "new_value_2": 2
}
```

### Frontend usage

- Navigate to **Concurrency Testing → Transaction Orchestrator**.
- Choose a scenario + isolation level, assign Node X / Node Y, and (optionally) supply the exact `order_id` + writer values.
- Click **Run Scenario** to spawn the asyncio workers; live logs appear instantly via SSE, while the status card polls for verdict/snapshots until the run finishes.
- Use **Abort Run** to simulate cancellations / rollbacks and watch the per-client step timeline update in place.

### Tests

Unit tests cover all builtin scenarios plus serialization-abort handling. Run them via:

```
python -m pytest replication/tests/test_orchestrator.py
```
