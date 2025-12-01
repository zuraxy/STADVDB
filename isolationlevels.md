
## Transaction Orchestrator (Concurrency Harness)

The FastAPI service now exposes a transaction orchestrator that can launch canned concurrency scenarios (and custom scripts) against the nodes. Use it to demonstrate isolation anomalies directly from the React UI (Concurrency tab → "Transaction Orchestrator") or by calling the REST endpoints below.

### REST endpoints

- `POST /orchestrator/run` — body requires `scenario` (`Case1_readers_only`, `Case2_writer_readers`, `Case3_concurrent_writers`, or `custom`), `isolation_level` (`READ_UNCOMMITTED`, `READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE`), `parallel_clients` (1-16), and optional `custom_transactions` (list of client scripts when `scenario=custom`). Returns `{ "run_id": "..." }`.
- `GET /orchestrator/status/{run_id}` — returns run metadata, per-client state, and a result summary (including node snapshots and detected serialization conflicts).
- `GET /orchestrator/logs/{run_id}` — streaming-friendly log feed for UI polling.
- `POST /orchestrator/abort/{run_id}` — cancels an in-flight run.

> ℹ️ PostgreSQL folds `READ_UNCOMMITTED` into `READ COMMITTED`; the orchestrator surfaces this note in both the API and UI so readers understand why dirty reads cannot be demonstrated directly.

#### Sample payload

```json
{
  "scenario": "Case3_concurrent_writers",
  "isolation_level": "SERIALIZABLE",
  "parallel_clients": 3
}
```

#### Custom scripts

Provide your own clients when `scenario` is `custom`:

```json
{
  "scenario": "custom",
  "isolation_level": "REPEATABLE_READ",
  "parallel_clients": 1,
  "custom_transactions": [
    {
      "node": "node0",
      "statements": [
        {"sql": "SELECT quantity FROM orders WHERE order_id = $1", "params": ["<uuid>"]},
        {"sql": "UPDATE orders SET quantity = quantity + 2 WHERE order_id = $1", "params": ["<uuid>"]}
      ]
    }
  ]
}
```

### Frontend usage

- Navigate to **Concurrency Testing → Transaction Orchestrator**.
- Pick a scenario, isolation level, and client count, then click **Run Scenario**.
- Status, per-client outcomes, node snapshots, and recent logs refresh automatically; you can also click **Abort Run** to simulate cancellations.

### Tests

Unit tests cover all builtin scenarios plus serialization-abort handling. Run them via:

```
python -m pytest replication/tests/test_orchestrator.py
```
