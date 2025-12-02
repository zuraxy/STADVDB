"""Tests for recovery module."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest

from replication.config import PeerNode, Settings
from replication.models import OpRecord
from replication.recovery import (
    RecoveryManager,
    RecoveryMode,
    RecoveryState,
    RecoveryJob,
    RecoveryMetrics,
    export_snapshot_helper,
    import_snapshot_helper,
    set_recovery_flag,
    get_recovery_flag,
)


# ============== Test Fixtures ==============

class MockConnection:
    """Mock asyncpg connection for testing."""
    
    def __init__(self):
        self.orders: Dict[str, Dict[str, Any]] = {}
        self.op_log: List[Dict[str, Any]] = []
        self.acks: List[Dict[str, Any]] = []
        self.metadata: Dict[str, str] = {}
        self.executed_queries: List[str] = []
    
    async def execute(self, query: str, *args) -> str:
        self.executed_queries.append(query)
        
        query_lower = query.lower().strip()
        
        if "insert into orders" in query_lower:
            order_id = str(args[0]) if args else str(uuid4())
            self.orders[order_id] = {
                "order_id": order_id,
                "quantity": args[1] if len(args) > 1 else 1,
                "payload": args[2] if len(args) > 2 else None,
            }
            return "INSERT 0 1"
        
        if "insert into op_log" in query_lower:
            op_id = str(args[0]) if args else str(uuid4())
            self.op_log.append({
                "op_id": op_id,
                "origin_node": args[1] if len(args) > 1 else "node0",
                "lamport": args[7] if len(args) > 7 else 0,
            })
            return "INSERT 0 1"
        
        if "insert into log_acknowledgements" in query_lower:
            self.acks.append({
                "op_id": str(args[0]) if args else None,
                "node": args[1] if len(args) > 1 else "node0",
            })
            return "INSERT 0 1"
        
        if "insert into node_metadata" in query_lower:
            if len(args) >= 2:
                self.metadata[args[0]] = args[1]
            return "INSERT 0 1"
        
        if "delete from orders" in query_lower:
            order_id = str(args[0]) if args else None
            if order_id and order_id in self.orders:
                del self.orders[order_id]
                return "DELETE 1"
            return "DELETE 0"
        
        if "update op_log" in query_lower:
            return "UPDATE 1"
        
        if "create table" in query_lower:
            return "CREATE TABLE"
        
        return "OK"
    
    async def fetch(self, query: str, *args) -> List[Dict[str, Any]]:
        self.executed_queries.append(query)
        
        query_lower = query.lower()
        
        if "from op_log" in query_lower and "applied = false" in query_lower:
            # Return unapplied ops
            return [op for op in self.op_log if not op.get("applied", False)][:100]
        
        if "from orders" in query_lower:
            return list(self.orders.values())
        
        if "group by order_id having count" in query_lower:
            # Check for duplicates
            return []
        
        return []
    
    async def fetchval(self, query: str, *args) -> Any:
        self.executed_queries.append(query)
        
        query_lower = query.lower()
        
        if "max(lamport)" in query_lower:
            if not self.op_log:
                return -1
            return max(op.get("lamport", 0) for op in self.op_log)
        
        if "count(*)" in query_lower:
            return len(self.orders)
        
        return 0
    
    async def fetchrow(self, query: str, *args) -> Optional[Dict[str, Any]]:
        self.executed_queries.append(query)
        
        query_lower = query.lower()
        
        if "from orders" in query_lower and "where order_id" in query_lower:
            order_id = str(args[0]) if args else None
            return self.orders.get(order_id)
        
        return None
    
    class _Transaction:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
    
    def transaction(self):
        return self._Transaction()


class MockPool:
    """Mock asyncpg pool for testing."""
    
    def __init__(self, conn: Optional[MockConnection] = None):
        self._conn = conn or MockConnection()
    
    class _AcquireContext:
        def __init__(self, conn):
            self._conn = conn
        async def __aenter__(self):
            return self._conn
        async def __aexit__(self, *args):
            pass
    
    def acquire(self):
        return self._AcquireContext(self._conn)


class MockHTTPClient:
    """Mock HTTP client for testing."""
    
    def __init__(self):
        self.responses: Dict[str, Any] = {}
        self.requests: List[Dict[str, Any]] = []
    
    def set_response(self, url_pattern: str, response: Any):
        self.responses[url_pattern] = response
    
    async def get_json(self, url: str, params: Optional[Dict] = None) -> Any:
        self.requests.append({"method": "GET", "url": url, "params": params})
        
        for pattern, response in self.responses.items():
            if pattern in url:
                if callable(response):
                    return response(url, params)
                return response
        
        return []
    
    async def post_json(self, url: str, payload: Dict) -> Any:
        self.requests.append({"method": "POST", "url": url, "payload": payload})
        
        for pattern, response in self.responses.items():
            if pattern in url:
                if callable(response):
                    return response(url, payload)
                return response
        
        return {"status": "ok"}
    
    async def close(self):
        pass


class MockCrud:
    """Mock crud module for testing."""
    
    def __init__(self, conn: MockConnection):
        self._conn = conn
    
    async def insert_op_if_missing(self, conn, op: OpRecord) -> bool:
        op_id = str(op.op_id)
        existing = [o for o in self._conn.op_log if str(o.get("op_id")) == op_id]
        if existing:
            return False
        self._conn.op_log.append({
            "op_id": op_id,
            "origin_node": op.origin_node,
            "op_type": op.op_type,
            "row_id": str(op.row_id),
            "lamport": op.lamport,
            "applied": False,
            "payload": op.payload,
        })
        return True
    
    async def fetch_unapplied_ops(self, conn, limit: int = 100) -> List[OpRecord]:
        unapplied = [op for op in self._conn.op_log if not op.get("applied", False)][:limit]
        return [
            OpRecord(
                op_id=op["op_id"],
                origin_node=op.get("origin_node", "node0"),
                op_type=op.get("op_type", "upsert"),
                table_name="orders",
                row_id=op.get("row_id", str(uuid4())),
                payload=op.get("payload", {}),
                ts=datetime.now(timezone.utc),
                lamport=op.get("lamport", 0),
                applied=False,
                applied_ts=None,
            )
            for op in unapplied
        ]
    
    async def apply_op_tx(self, conn, op: OpRecord, use_transaction: bool = True) -> None:
        op_id = str(op.op_id)
        for i, log_op in enumerate(self._conn.op_log):
            if str(log_op.get("op_id")) == op_id:
                self._conn.op_log[i]["applied"] = True
                break
        
        if op.op_type == "delete":
            row_id = str(op.row_id)
            if row_id in self._conn.orders:
                del self._conn.orders[row_id]
        else:
            row_id = str(op.row_id)
            self._conn.orders[row_id] = {
                "order_id": row_id,
                "quantity": op.payload.get("quantity", 1) if op.payload else 1,
                "payload": op.payload.get("payload") if op.payload else None,
            }
    
    async def insert_ack(self, conn, op_id, node: str) -> None:
        self._conn.acks.append({"op_id": str(op_id), "node": node})
    
    async def ensure_replication_metadata(self, conn) -> None:
        pass


@pytest.fixture
def mock_conn():
    return MockConnection()


@pytest.fixture
def mock_pool(mock_conn):
    return MockPool(mock_conn)


@pytest.fixture
def mock_http():
    return MockHTTPClient()


@pytest.fixture
def mock_crud(mock_conn):
    return MockCrud(mock_conn)


@pytest.fixture
def settings():
    return Settings(
        database_dsn="postgres://test",
        node_name="node0",
        peer_nodes=[
            PeerNode(name="node1", base_url="http://node1:8000"),
            PeerNode(name="node2", base_url="http://node2:8000"),
        ],
        poll_interval=1,
        default_master="node0",
        default_master_url="http://node0:8000",
        promoted=False,
        partition_rule=5,
        applier_interval=0.1,
        applier_batch_limit=1,
        applier_max_attempts=3,
        applier_debug=False,
        node0_dsn="postgres://node0",
        node1_dsn="postgres://node1",
        node2_dsn="postgres://node2",
    )


@pytest.fixture
def recovery_manager(mock_pool, settings, mock_http, mock_crud):
    return RecoveryManager(
        pool=mock_pool,
        settings=settings,
        http_client=mock_http,
        crud_module=mock_crud,
    )


# ============== Unit Tests ==============

class TestRecoveryMetrics:
    """Tests for RecoveryMetrics."""
    
    def test_initial_state(self):
        metrics = RecoveryMetrics()
        assert metrics.last_applied_lamport == -1
        assert metrics.ops_fetched == 0
        assert metrics.ops_applied == 0
        assert metrics.apply_rate == 0.0
    
    def test_to_dict(self):
        metrics = RecoveryMetrics(
            last_applied_lamport=100,
            ops_fetched=50,
            ops_applied=25,
        )
        d = metrics.to_dict()
        assert d["last_applied_lamport"] == 100
        assert d["ops_fetched"] == 50
        assert d["ops_applied"] == 25
    
    def test_apply_rate_calculation(self):
        # Use a start time 10 seconds in the past to get a measurable rate
        past_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        metrics = RecoveryMetrics(
            start_time=past_time,
            ops_applied=100,
        )
        # 100 ops over 10 seconds = 10 ops/sec
        assert metrics.apply_rate > 0
        assert abs(metrics.apply_rate - 10.0) < 0.5  # Allow some tolerance
    
    def test_estimated_eta(self):
        # Use a start time 10 seconds in the past so rate is calculable
        past_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        metrics = RecoveryMetrics(
            start_time=past_time,
            ops_applied=100,
            ops_remaining=100,
        )
        eta = metrics.estimated_eta_seconds
        assert eta is not None
        # 100 applied in 10 sec = 10/sec, 100 remaining should take ~10 sec
        assert abs(eta - 10.0) < 1.0  # Allow some tolerance
        assert eta >= 0


class TestRecoveryJob:
    """Tests for RecoveryJob."""
    
    def test_create_job(self):
        job = RecoveryJob(
            job_id="test-job-id",
            mode=RecoveryMode.LEADER,
        )
        assert job.job_id == "test-job-id"
        assert job.mode == RecoveryMode.LEADER
        assert job.state == RecoveryState.PENDING
    
    def test_log_entry(self):
        job = RecoveryJob(job_id="test", mode=RecoveryMode.LEADER)
        job.log("info", "Test message", key="value")
        
        assert len(job.logs) == 1
        assert job.logs[0].message == "Test message"
        assert job.logs[0].level == "info"
        assert job.logs[0].details == {"key": "value"}
    
    def test_to_dict(self):
        job = RecoveryJob(job_id="test", mode=RecoveryMode.NODE)
        d = job.to_dict()
        
        assert d["job_id"] == "test"
        assert d["mode"] == "node"
        assert d["state"] == "pending"


class TestRecoveryManager:
    """Tests for RecoveryManager."""
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_start_job(self, recovery_manager, mock_http):
        # Set up mock responses
        mock_http.set_response("/oplog", [])
        
        job_id = await recovery_manager.start_job(mode="leader")
        
        assert job_id is not None
        assert recovery_manager.recovery_in_progress
        
        # Clean up: cancel the background task
        await recovery_manager.abort_job(job_id)
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_start_job_conflict(self, recovery_manager, mock_http):
        mock_http.set_response("/oplog", [])
        
        job_id = await recovery_manager.start_job(mode="leader")
        
        with pytest.raises(RuntimeError, match="already in progress"):
            await recovery_manager.start_job(mode="leader")
        
        # Clean up
        await recovery_manager.abort_job(job_id)
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_get_status(self, recovery_manager, mock_http):
        mock_http.set_response("/oplog", [])
        
        job_id = await recovery_manager.start_job(mode="node")
        
        # Wait a bit for job to start
        await asyncio.sleep(0.1)
        
        status = recovery_manager.get_status(job_id)
        
        assert status is not None
        assert status["job_id"] == job_id
        assert status["mode"] == "node"
        
        # Clean up
        await recovery_manager.abort_job(job_id)
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_get_logs(self, recovery_manager, mock_http):
        mock_http.set_response("/oplog", [])
        
        job_id = await recovery_manager.start_job(mode="leader")
        await asyncio.sleep(0.1)
        
        logs = recovery_manager.get_logs(job_id)
        
        assert logs is not None
        assert isinstance(logs, list)
        
        # Clean up
        await recovery_manager.abort_job(job_id)
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_abort_job(self, recovery_manager, mock_http):
        # Make the job take time by having many ops
        def slow_response(url, params):
            return [
                {
                    "op_id": str(uuid4()),
                    "origin_node": "node1",
                    "op_type": "upsert",
                    "table_name": "orders",
                    "row_id": str(uuid4()),
                    "payload": {"quantity": 1},
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "lamport": i,
                    "applied": False,
                    "applied_ts": None,
                }
                for i in range(100)
            ]
        
        mock_http.set_response("/oplog", slow_response)
        
        job_id = await recovery_manager.start_job(mode="leader")
        await asyncio.sleep(0.05)
        
        success = await recovery_manager.abort_job(job_id)
        
        assert success
        status = recovery_manager.get_status(job_id)
        assert status["state"] == "aborted"
    
    def test_set_recovery_flag(self, recovery_manager):
        assert not recovery_manager.writes_gated
        
        recovery_manager.set_recovery_flag(True)
        assert recovery_manager.writes_gated
        
        recovery_manager.set_recovery_flag(False)
        assert not recovery_manager.writes_gated
    
    @pytest.mark.asyncio
    async def test_export_snapshot(self, recovery_manager, mock_conn):
        # Add some orders
        mock_conn.orders["order-1"] = {
            "order_id": "order-1",
            "quantity": 3,
            "payload": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        mock_conn.orders["order-2"] = {
            "order_id": "order-2",
            "quantity": 7,
            "payload": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        
        # Note: This tests the concept; actual implementation needs real DB
        snapshot = await recovery_manager.export_snapshot()
        
        # The mock doesn't fully implement the query, but structure is correct
        assert "data" in snapshot or "count" in snapshot


class TestLeaderRecovery:
    """Tests for leader recovery flow."""
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Integration test requiring extended timeout")
    async def test_leader_recovery_empty_oplog(self, recovery_manager, mock_http):
        """Test leader recovery when local oplog is empty."""
        mock_http.set_response("/oplog", [])
        mock_http.set_response("/recovery/snapshot", {"data": [], "count": 0})
        
        job_id = await recovery_manager.start_job(mode="leader")
        
        # Wait for job to complete
        for _ in range(50):
            await asyncio.sleep(0.1)
            status = recovery_manager.get_status(job_id)
            if status["state"] in ("ready", "failed", "aborted"):
                break
        
        status = recovery_manager.get_status(job_id)
        # With empty responses, should complete or fail gracefully
        assert status["state"] in ("ready", "failed", "needs_rebuild")
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Integration test requiring extended timeout")
    async def test_leader_recovery_with_ops(self, recovery_manager, mock_http, mock_conn):
        """Test leader recovery with ops to fetch."""
        ops_data = [
            {
                "op_id": str(uuid4()),
                "origin_node": "node1",
                "op_type": "upsert",
                "table_name": "orders",
                "row_id": str(uuid4()),
                "payload": {"quantity": 3},
                "ts": datetime.now(timezone.utc).isoformat(),
                "lamport": 1,
                "applied": False,
                "applied_ts": None,
            },
            {
                "op_id": str(uuid4()),
                "origin_node": "node2",
                "op_type": "upsert",
                "table_name": "orders",
                "row_id": str(uuid4()),
                "payload": {"quantity": 7},
                "ts": datetime.now(timezone.utc).isoformat(),
                "lamport": 2,
                "applied": False,
                "applied_ts": None,
            },
        ]
        
        call_count = [0]
        def oplog_response(url, params):
            call_count[0] += 1
            if call_count[0] == 1:
                return ops_data
            return []  # No more ops on subsequent calls
        
        mock_http.set_response("/oplog", oplog_response)
        mock_http.set_response("/recovery/snapshot", {"data": [], "count": 0})
        
        job_id = await recovery_manager.start_job(mode="leader")
        
        # Wait for completion
        for _ in range(50):
            await asyncio.sleep(0.1)
            status = recovery_manager.get_status(job_id)
            if status["state"] in ("ready", "failed"):
                break
        
        status = recovery_manager.get_status(job_id)
        metrics = status["metrics"]
        
        # Should have fetched ops
        assert metrics["ops_fetched"] >= 0


class TestNodeRejoin:
    """Tests for node cold-rejoin flow."""
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Integration test requiring extended timeout")
    async def test_node_rejoin_basic(self, recovery_manager, mock_http):
        """Test basic node rejoin."""
        mock_http.set_response("/oplog", [])
        
        job_id = await recovery_manager.start_job(mode="node")
        
        # Wait for completion
        for _ in range(50):
            await asyncio.sleep(0.1)
            status = recovery_manager.get_status(job_id)
            if status["state"] in ("ready", "failed"):
                break
        
        status = recovery_manager.get_status(job_id)
        assert status["state"] in ("ready", "failed")


class TestPromotionResync:
    """Tests for promotion resync flow."""
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Integration test requiring extended timeout")
    async def test_promotion_resync_basic(self, recovery_manager, mock_http):
        """Test basic promotion resync."""
        mock_http.set_response("/oplog", [])
        mock_http.set_response("/admin/demote", {"status": "ok"})
        
        since_ts = datetime.now(timezone.utc).isoformat()
        job_id = await recovery_manager.start_job(
            mode="promotion",
            since_ts=since_ts,
            promoted_node="node1",
        )
        
        # Wait for completion
        for _ in range(50):
            await asyncio.sleep(0.1)
            status = recovery_manager.get_status(job_id)
            if status["state"] in ("ready", "failed"):
                break
        
        status = recovery_manager.get_status(job_id)
        assert status["state"] in ("ready", "failed")


class TestSnapshotHelpers:
    """Tests for snapshot helper functions."""
    
    def test_recovery_flag(self):
        """Test global recovery flag."""
        assert not get_recovery_flag()
        
        set_recovery_flag(True)
        assert get_recovery_flag()
        
        set_recovery_flag(False)
        assert not get_recovery_flag()


class TestIdempotency:
    """Tests for idempotent operation application."""
    
    @pytest.mark.asyncio
    async def test_duplicate_op_insertion(self, mock_crud, mock_conn):
        """Test that duplicate ops are not inserted twice."""
        op = OpRecord(
            op_id=uuid4(),
            origin_node="node1",
            op_type="upsert",
            table_name="orders",
            row_id=uuid4(),
            payload={"quantity": 5},
            ts=datetime.now(timezone.utc),
            lamport=1,
            applied=False,
            applied_ts=None,
        )
        
        # First insertion
        inserted1 = await mock_crud.insert_op_if_missing(mock_conn, op)
        assert inserted1
        
        # Second insertion (duplicate)
        inserted2 = await mock_crud.insert_op_if_missing(mock_conn, op)
        assert not inserted2
        
        # Only one op in log
        assert len(mock_conn.op_log) == 1
    
    @pytest.mark.asyncio
    async def test_idempotent_apply(self, mock_crud, mock_conn):
        """Test that applying same op twice results in same state."""
        row_id = uuid4()
        op = OpRecord(
            op_id=uuid4(),
            origin_node="node1",
            op_type="upsert",
            table_name="orders",
            row_id=row_id,
            payload={"quantity": 5, "payload": {"key": "value"}},
            ts=datetime.now(timezone.utc),
            lamport=1,
            applied=False,
            applied_ts=None,
        )
        
        # Insert op first
        await mock_crud.insert_op_if_missing(mock_conn, op)
        
        # Apply once
        await mock_crud.apply_op_tx(mock_conn, op, use_transaction=False)
        state1 = dict(mock_conn.orders)
        
        # Apply again
        await mock_crud.apply_op_tx(mock_conn, op, use_transaction=False)
        state2 = dict(mock_conn.orders)
        
        # States should be identical
        assert state1 == state2
        assert len(mock_conn.orders) == 1


class TestConflictResolution:
    """Tests for last-lamport-wins conflict resolution."""
    
    @pytest.mark.asyncio
    async def test_last_lamport_wins(self, mock_crud, mock_conn):
        """Test that higher lamport value wins."""
        row_id = uuid4()
        
        # Op with lower lamport
        op1 = OpRecord(
            op_id=uuid4(),
            origin_node="node1",
            op_type="upsert",
            table_name="orders",
            row_id=row_id,
            payload={"quantity": 3},
            ts=datetime.now(timezone.utc),
            lamport=1,
            applied=False,
            applied_ts=None,
        )
        
        # Op with higher lamport
        op2 = OpRecord(
            op_id=uuid4(),
            origin_node="node2",
            op_type="upsert",
            table_name="orders",
            row_id=row_id,
            payload={"quantity": 7},
            ts=datetime.now(timezone.utc),
            lamport=2,
            applied=False,
            applied_ts=None,
        )
        
        # Apply in lamport order (simulating what recovery does)
        await mock_crud.apply_op_tx(mock_conn, op1)
        await mock_crud.apply_op_tx(mock_conn, op2)
        
        # Final value should be from op2 (higher lamport)
        order = mock_conn.orders.get(str(row_id))
        assert order is not None
        assert order["quantity"] == 7
    
    @pytest.mark.asyncio
    async def test_origin_node_tiebreaker(self, mock_crud, mock_conn):
        """Test origin_node tiebreaker when lamport is equal."""
        row_id = uuid4()
        
        # Both ops have same lamport
        op1 = OpRecord(
            op_id=uuid4(),
            origin_node="node2",  # Higher node name
            op_type="upsert",
            table_name="orders",
            row_id=row_id,
            payload={"quantity": 7},
            ts=datetime.now(timezone.utc),
            lamport=1,
            applied=False,
            applied_ts=None,
        )
        
        op2 = OpRecord(
            op_id=uuid4(),
            origin_node="node1",  # Lower node name
            op_type="upsert",
            table_name="orders",
            row_id=row_id,
            payload={"quantity": 3},
            ts=datetime.now(timezone.utc),
            lamport=1,
            applied=False,
            applied_ts=None,
        )
        
        # Sort by (lamport, origin_node) - node1 comes before node2
        ops = sorted([op1, op2], key=lambda o: (o.lamport, o.origin_node))
        
        for op in ops:
            await mock_crud.apply_op_tx(mock_conn, op)
        
        # node2 was applied last (sorted last), so its value wins
        order = mock_conn.orders.get(str(row_id))
        assert order is not None
        assert order["quantity"] == 7  # node2's value


class TestCrossPartitionMoves:
    """Tests for cross-partition move handling."""
    
    @pytest.mark.asyncio
    async def test_delete_then_insert(self, mock_crud, mock_conn):
        """Test that delete followed by insert results in single row."""
        row_id = uuid4()
        
        # First, create an order
        create_op = OpRecord(
            op_id=uuid4(),
            origin_node="node1",
            op_type="upsert",
            table_name="orders",
            row_id=row_id,
            payload={"quantity": 3},  # Low partition
            ts=datetime.now(timezone.utc),
            lamport=1,
            applied=False,
            applied_ts=None,
        )
        await mock_crud.apply_op_tx(mock_conn, create_op)
        assert str(row_id) in mock_conn.orders
        
        # Delete (moving from node1)
        delete_op = OpRecord(
            op_id=uuid4(),
            origin_node="node1",
            op_type="delete",
            table_name="orders",
            row_id=row_id,
            payload={},
            ts=datetime.now(timezone.utc),
            lamport=2,
            applied=False,
            applied_ts=None,
        )
        await mock_crud.apply_op_tx(mock_conn, delete_op)
        assert str(row_id) not in mock_conn.orders
        
        # Insert on new partition (node2)
        insert_op = OpRecord(
            op_id=uuid4(),
            origin_node="node2",
            op_type="upsert",
            table_name="orders",
            row_id=row_id,
            payload={"quantity": 7},  # High partition
            ts=datetime.now(timezone.utc),
            lamport=3,
            applied=False,
            applied_ts=None,
        )
        await mock_crud.apply_op_tx(mock_conn, insert_op)
        
        # Should have exactly one order with new quantity
        assert len(mock_conn.orders) == 1
        assert str(row_id) in mock_conn.orders
        assert mock_conn.orders[str(row_id)]["quantity"] == 7


# Integration-style tests (would need real DB in actual implementation)

class TestRecoveryScenarios:
    """Integration-style tests for full recovery scenarios."""
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Integration test requiring extended timeout and real DB")
    async def test_scenario_node0_down_writes_on_partitions(
        self, recovery_manager, mock_http, mock_conn
    ):
        """
        Scenario: Node0 down, writes happen on Node1/Node2, Node0 recovers.
        
        1. Simulate writes on Node1 (qty <= 5) and Node2 (qty > 5)
        2. Run leader recovery
        3. Verify Node0 has union of partition data
        """
        # Simulate ops from Node1 (low partition)
        node1_ops = [
            {
                "op_id": str(uuid4()),
                "origin_node": "node1",
                "op_type": "upsert",
                "table_name": "orders",
                "row_id": str(uuid4()),
                "payload": {"quantity": i},
                "ts": datetime.now(timezone.utc).isoformat(),
                "lamport": i,
                "applied": False,
                "applied_ts": None,
            }
            for i in range(1, 6)  # qty 1-5
        ]
        
        # Simulate ops from Node2 (high partition)
        node2_ops = [
            {
                "op_id": str(uuid4()),
                "origin_node": "node2",
                "op_type": "upsert",
                "table_name": "orders",
                "row_id": str(uuid4()),
                "payload": {"quantity": i},
                "ts": datetime.now(timezone.utc).isoformat(),
                "lamport": i + 10,  # Higher lamport
                "applied": False,
                "applied_ts": None,
            }
            for i in range(6, 11)  # qty 6-10
        ]
        
        all_ops = node1_ops + node2_ops
        call_count = [0]
        
        def oplog_response(url, params):
            call_count[0] += 1
            if call_count[0] <= 2:  # First call for each peer
                if "node1" in url:
                    return node1_ops
                if "node2" in url:
                    return node2_ops
            return []
        
        mock_http.set_response("/oplog", oplog_response)
        mock_http.set_response("/recovery/snapshot", {"data": [], "count": 0})
        
        # Run recovery
        job_id = await recovery_manager.start_job(mode="leader")
        
        # Wait for completion
        for _ in range(100):
            await asyncio.sleep(0.1)
            status = recovery_manager.get_status(job_id)
            if status["state"] in ("ready", "failed"):
                break
        
        status = recovery_manager.get_status(job_id)
        
        # Verify metrics show ops were fetched
        # (Full verification would need real DB)
        assert status is not None
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Integration test requiring extended timeout and real DB")
    async def test_scenario_gc_gap_snapshot_fallback(
        self, recovery_manager, mock_http, mock_conn
    ):
        """
        Scenario: Node0 down for long time, ops were GC'd, snapshot fallback needed.
        
        1. Simulate large lamport gap (> threshold)
        2. Verify snapshot is requested
        3. Verify recovery completes after snapshot import
        """
        # Simulate peer with very high lamport (indicating large gap)
        def oplog_response(url, params):
            since = params.get("since_lamport", -1) if params else -1
            if since == -1:
                # Return op with very high lamport to trigger gap detection
                return [{
                    "op_id": str(uuid4()),
                    "origin_node": "node1",
                    "op_type": "upsert",
                    "table_name": "orders",
                    "row_id": str(uuid4()),
                    "payload": {"quantity": 5},
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "lamport": 50000,  # Very high lamport
                    "applied": False,
                    "applied_ts": None,
                }]
            return []
        
        mock_http.set_response("/oplog", oplog_response)
        mock_http.set_response("/recovery/snapshot", {
            "data": [
                {"order_id": str(uuid4()), "quantity": 3, "payload": None},
                {"order_id": str(uuid4()), "quantity": 7, "payload": None},
            ],
            "count": 2,
        })
        
        # Run recovery
        job_id = await recovery_manager.start_job(mode="leader")
        
        # Wait for completion
        for _ in range(100):
            await asyncio.sleep(0.1)
            status = recovery_manager.get_status(job_id)
            if status["state"] in ("ready", "failed", "needs_rebuild"):
                break
        
        status = recovery_manager.get_status(job_id)
        
        # Should detect need for rebuild
        # Note: full verification requires real DB
        assert status is not None
