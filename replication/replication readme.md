# Distributed Replication Service

This project provides a FastAPI-based service that runs on every node (Node0/Node1/Node2) inside the Proxmox cluster. Each node exposes CRUD APIs for `orders`, a pull-based replication endpoint, and background workers that replicate and apply operations using Postgres 18 + asyncpg.

## Architecture Overview

- **FastAPI app (`app/main.py`)** – mounts CRUD, replication, and admin routes and orchestrates background workers.
- **Replication model** – every node polls its peers every 5 seconds via `GET /oplog?since_lamport=<n>`, inserts missing ops, and keeps Lamport ordering guarantees when applying them.
- **Applier worker** – replays local `op_log` rows (idempotent upserts) into `orders` and writes acknowledgements into `log_acknowledgements`.
- **Routing rules** – all writes flow to the configured master (default `node0`). A node can be promoted via `/promote` to accept partitioned writes (Node1 `qty <= PARTITION_RULE`, Node2 `qty > PARTITION_RULE`).
- **Delivery semantics** – at-least-once; op application relies on `INSERT ... ON CONFLICT` to remain idempotent.

## Environment Variables

See `.env.example` for a ready-to-edit template. Core values:

| Variable | Description |
| --- | --- |
| `DATABASE_DSN` | Postgres DSN for the node-local database. |
| `NODE_NAME` | Logical name (`node0`, `node1`, `node2`). |
| `DEFAULT_MASTER` / `DEFAULT_MASTER_URL` | Name/url of the master that should receive writes. |
| `PEER_NODES` | JSON array or comma list of peers. Supports `name=url` format. |
| `POLL_INTERVAL` | Seconds between replication polls (default 5). |
| `APPLIER_INTERVAL` | Seconds between applier batches (default 2). |
| `PROMOTED` | Boot-time promotion flag (use `/promote` for runtime changes). |
| `PARTITION_RULE` | Quantity threshold for partitioned writes (default 5). |

## Getting Started

1. **Install dependencies**
   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate   # PowerShell on Windows
   pip install -r requirements.txt  # add fastapi, uvicorn, asyncpg, httpx, pytest, pytest-asyncio
   ```
2. **Configure Postgres** – ensure each node DB contains the required tables shown in `DEPLOYMENT.md` (orders, op_log, log_acknowledgements).
3. **Copy environment file**
   ```bash
   cp .env.example .env
   # edit .env with per-node DSN, NODE_NAME, ports, peer URLs
   ```

## Running Locally (multi-node simulation)

Run three shells, each with its own port + env overrides:

```bash
# Node0 (master)
set DATABASE_DSN=postgresql://postgres:postgres@localhost:5432/node0db
set NODE_NAME=node0
set DEFAULT_MASTER=node0
set DEFAULT_MASTER_URL=http://localhost:8000
set PEER_NODES=[{"name":"node0","url":"http://localhost:8000"},{"name":"node1","url":"http://localhost:8001"},{"name":"node2","url":"http://localhost:8002"}]
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Node1 (partition qty <= 5)
set NODE_NAME=node1
set DATABASE_DSN=postgresql://postgres:postgres@localhost:5433/node1db
uvicorn app.main:app --host 0.0.0.0 --port 8001

# Node2 (partition qty > 5)
set NODE_NAME=node2
set DATABASE_DSN=postgresql://postgres:postgres@localhost:5434/node2db
uvicorn app.main:app --host 0.0.0.0 --port 8002
```

Each replica automatically starts replication + applier workers after connecting to its database.

## CRUD + Admin APIs

- `POST /orders` – Creates an order on the master or permitted promoted node. Body matches `OrderCreate` (quantity + payload + optional UUID).
- `GET /orders/{order_id}?local=true` – Read locally (for stale view) or proxy to master.
- `PUT /orders/{order_id}` / `DELETE /orders/{order_id}` – Update/delete with the same routing semantics as create.
- `GET /oplog` – Peer pull endpoint returning ops ordered by Lamport + origin.
- `GET /health` – DB connectivity check.
- `GET /status/replication` – Exposes worker metrics, last seen Lamport per peer, and applier stats.
- `POST /promote {"promote": true}` – Toggle promotion flag to allow partitioned writes when the master is unavailable (remember to demote later to avoid split brain). Future cross-partition transactions are marked as TODO in the code.

## Simulating Failover

1. Start Node0, Node1, Node2 as above.
2. Stop Node0.
3. On Node1 call `POST /promote` with `{"promote": true}`.
4. Submit `POST /orders` with `quantity <= PARTITION_RULE` to Node1. Requests outside the partition still fail until master returns.
5. When Node0 is back, call `POST /promote {"promote": false}` on Node1/Node2.

## Tests

Unit tests focus on worker logic (poller + applier) using pytest + asyncio:

```bash
pytest app/tests
```

The tests mock peer responses and DB interactions to keep feedback tight. Integration tests against a live Postgres + multiple FastAPI processes can be layered on later.

## Roadmap / TODOs

- Implement `/workers/gc.py` once quorum-wide acknowledgement tracking is in place.
- Add cross-partition distributed transaction coordinator (currently marked as TODO around the write path).
- Expand unit tests to cover HTTP forwarding + partition enforcement.
- Provide docker-compose for local tri-node setups if needed later.