
## Transaction Orchestrator (Concurrency Harness)

The FastAPI service now exposes a transaction orchestrator that can launch canned concurrency scenarios (and custom scripts) against the nodes. Use it to demonstrate isolation anomalies directly from the React UI (Concurrency tab → "Transaction Orchestrator") or by calling the REST endpoints below.

### REST endpoints

- `POST /orchestrator/run` — Body requires a `scenario` (`READ_READ`, `READ_WRITE`, or `WRITE_WRITE`), optional `order_id`, and **exactly two** `actors`. Each actor defines `name`, `node` (`node0`/`node1`/`node2`), `isolation_level`, optional `delay_seconds`, and (for writers only) a `new_quantity`. Returns `{ "run_id": "..." }` once the transactions are queued.
- `GET /orchestrator/status/{run_id}` — returns run metadata, per-client state, isolation overview, actor observations, and node snapshots.
- `GET /orchestrator/logs/{run_id}` — streaming-friendly log feed for UI polling.
- `POST /orchestrator/abort/{run_id}` — cancels an in-flight run.

> ℹ️ PostgreSQL folds `READ_UNCOMMITTED` into `READ COMMITTED`; the orchestrator surfaces this note per actor so it is obvious why dirty reads cannot be demonstrated directly.

#### Sample payload

```json
{
  "scenario": "READ_WRITE",
  "order_id": "3f911688-9c02-4b4f-8f24-5b8c2d7f2d41",
  "actors": [
    {
      "name": "reader_a",
      "node": "node0",
      "isolation_level": "REPEATABLE_READ",
      "delay_seconds": 0.25
    },
    {
      "name": "writer_b",
      "node": "node0",
      "isolation_level": "SERIALIZABLE",
      "delay_seconds": 0.1,
      "new_quantity": 12
    }
  ]
}
```

### Frontend usage

- Navigate to **Concurrency Testing → Transaction Orchestrator**.
- Pick a scenario, optionally target an order ID, configure the two transaction actors (node, isolation, pg_sleep delay, and new quantity for writers), then click **Run Scenario**.
- Status, per-actor outcomes, node snapshots, and recent logs refresh automatically; you can also click **Abort Run** to simulate cancellations.

### Tests

Unit tests cover all builtin scenarios plus serialization-abort handling. Run them via:

```
python -m pytest replication/tests/test_orchestrator.py
```
