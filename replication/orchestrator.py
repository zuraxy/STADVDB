"""Transaction orchestrator for concurrent scenario execution."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import asyncpg

from .config import Settings
from .utils import lamport as lamport_utils

LOGGER = logging.getLogger(__name__)


class IsolationLevel(str, Enum):
    """Supported isolation levels for orchestration runs."""

    READ_UNCOMMITTED = "READ_UNCOMMITTED"
    READ_COMMITTED = "READ_COMMITTED"
    REPEATABLE_READ = "REPEATABLE_READ"
    SERIALIZABLE = "SERIALIZABLE"

    @property
    def sql_clause(self) -> str:
        mapping = {
            IsolationLevel.READ_UNCOMMITTED: "READ COMMITTED",  # Postgres maps to READ COMMITTED
            IsolationLevel.READ_COMMITTED: "READ COMMITTED",
            IsolationLevel.REPEATABLE_READ: "REPEATABLE READ",
            IsolationLevel.SERIALIZABLE: "SERIALIZABLE",
        }
        return mapping[self]

    @property
    def note(self) -> Optional[str]:
        if self is IsolationLevel.READ_UNCOMMITTED:
            return "Postgres treats READ UNCOMMITTED as READ COMMITTED"
        return None


class ScenarioType(str, Enum):
    """Supported concurrency scenarios."""

    READ_READ = "READ_READ"
    READ_WRITE = "READ_WRITE"
    WRITE_WRITE = "WRITE_WRITE"
    NON_REPEATABLE_READ = "NON_REPEATABLE_READ"  # Reader reads twice, writer updates in between
    PHANTOM_READ = "PHANTOM_READ"  # Reader scans range twice, writer inserts in between

    @property
    def roles(self) -> Tuple[str, str]:
        mapping = {
            ScenarioType.READ_READ: ("read", "read"),
            ScenarioType.READ_WRITE: ("write", "read"),  # Writer first (on node_x), Reader second (on node_y)
            ScenarioType.WRITE_WRITE: ("write", "write"),
            ScenarioType.NON_REPEATABLE_READ: ("read", "write"),  # Reader first, writer updates
            ScenarioType.PHANTOM_READ: ("read_range", "insert"),  # Reader scans, writer inserts
        }
        return mapping[self]


@dataclass
class TransactionActorInput:
    """User-specified parameters per transaction actor."""

    name: str
    node: str
    isolation_level: IsolationLevel
    delay_seconds: float = 0.0
    new_quantity: Optional[int] = None
    auto_increment: bool = False  # If True, increment quantity by 1 instead of setting


@dataclass
class ActorPlan:
    """Resolved actor plan with computed role and normalized attributes."""

    actor_id: str
    node: str
    role: str
    isolation_level: IsolationLevel
    delay_seconds: float
    new_quantity: Optional[int]
    auto_increment: bool = False


@dataclass
class OrchestrationInput:
    scenario: ScenarioType
    actors: List[TransactionActorInput]
    order_id: Optional[UUID] = None


class RunState:
    """Mutable state for an orchestration run."""

    def __init__(self, run_id: str, payload: OrchestrationInput):
        self.id = run_id
        self.payload = payload
        self.status: str = "running"
        self.created_at = datetime.now(timezone.utc)
        self.finished_at: Optional[datetime] = None
        self.logs: List[Dict[str, Any]] = []
        self.client_status: Dict[str, Dict[str, Any]] = {}
        self.summary: Optional[Dict[str, Any]] = None
        self.cancel_event = asyncio.Event()
        self.main_task: Optional[asyncio.Task] = None
        self._log_lock = asyncio.Lock()
        self.order_id: Optional[UUID] = None
        self.initial_quantity: Optional[int] = None
        self.serialization_conflicts: List[str] = []
        self.actor_results: Dict[str, Dict[str, Any]] = {}
        self.actor_levels: Dict[str, IsolationLevel] = {}
        self.execution_times: Dict[str, Dict[str, float]] = {}  # Track execution times per actor

    async def log(self, event: str, **details: Any) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "details": details,
        }
        async with self._log_lock:
            self.logs.append(entry)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "run_id": self.id,
            "scenario": self.payload.scenario.value,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "clients": self.client_status,
            "result_summary": self.summary,
        }

    def mark_finished(self, status: str) -> None:
        self.status = status
        self.finished_at = datetime.now(timezone.utc)


class TransactionOrchestrator:
    """Coordinates concurrent SQL transactions across selectable nodes."""

    def __init__(
        self,
        settings: Settings,
        promoted_flag: Callable[[], bool],
        connection_factory: Optional[Callable[[str], Awaitable[asyncpg.Connection]]] = None,
        http_client: Optional[Any] = None,
    ):
        self.settings = settings
        self._promoted_flag = promoted_flag
        self._runs: Dict[str, RunState] = {}
        self._run_lock = asyncio.Lock()
        self._connection_factory = connection_factory or (lambda dsn: asyncpg.connect(dsn=dsn))
        self._node_dsns = self._build_node_dsn_map()
        self._http_client = http_client
        self._node_urls = self._build_node_url_map()

    def _build_node_dsn_map(self) -> Dict[str, Optional[str]]:
        mapping = {
            "node0": self.settings.node0_dsn or self.settings.database_dsn,
            "node1": self.settings.node1_dsn,
            "node2": self.settings.node2_dsn,
        }
        local_key = self.settings.node_name.lower()
        mapping[local_key] = self.settings.database_dsn
        return mapping

    def _build_node_url_map(self) -> Dict[str, Optional[str]]:
        """Build a mapping from node names to their HTTP base URLs."""
        mapping: Dict[str, Optional[str]] = {}
        # Local node doesn't need a URL (we use direct DB connection)
        local_key = self.settings.node_name.lower()
        mapping[local_key] = None  # None means use local DB
        # Map peer nodes from config
        for peer in self.settings.peer_nodes:
            peer_key = peer.name.lower()
            mapping[peer_key] = peer.base_url
        return mapping

    def _is_local_node(self, node: str) -> bool:
        """Check if the given node is the local node."""
        return node.lower() == self.settings.node_name.lower()

    def _primary_node(self) -> str:
        if self.settings.node_name == self.settings.default_master:
            return self.settings.default_master
        if self._promoted_flag():
            return self.settings.node_name
        return self.settings.default_master

    async def start_run(self, payload: OrchestrationInput) -> RunState:
        run_id = str(uuid4())
        state = RunState(run_id, payload)
        async with self._run_lock:
            self._runs[run_id] = state
        state.main_task = asyncio.create_task(self._execute_run(state))
        return state

    async def abort_run(self, run_id: str) -> bool:
        state = self._runs.get(run_id)
        if not state:
            return False
        state.cancel_event.set()
        if state.main_task:
            state.main_task.cancel()
        state.mark_finished("aborted")
        await state.log("run_aborted")
        return True

    def get_status(self, run_id: str) -> Optional[Dict[str, Any]]:
        state = self._runs.get(run_id)
        return state.snapshot() if state else None

    def get_logs(self, run_id: str) -> Optional[Dict[str, Any]]:
        state = self._runs.get(run_id)
        if not state:
            return None
        return {"run_id": run_id, "logs": state.logs}

    async def wait_for_run(self, run_id: str, timeout: float = 30.0) -> None:
        state = self._runs.get(run_id)
        if not state or not state.main_task:
            return
        await asyncio.wait_for(state.main_task, timeout)

    async def _execute_run(self, state: RunState) -> None:
        try:
            order_id, quantity = await self._resolve_target_order(state.payload.order_id)
            state.order_id = order_id
            state.initial_quantity = quantity
            plans = self._prepare_plans(state)
            await state.log(
                "scenario_compiled",
                order_id=str(order_id),
                actors=[plan.actor_id for plan in plans],
            )
            
            # For READ_WRITE scenario: writer executes first, reader follows
            # This allows testing dirty reads (reader sees uncommitted) or 
            # committed reads (reader sees after commit)
            if state.payload.scenario == ScenarioType.READ_WRITE and len(plans) == 2:
                writer_plan = plans[0]  # First actor is writer
                reader_plan = plans[1]  # Second actor is reader
                
                # Start writer first
                writer_task = asyncio.create_task(self._execute_actor(state, writer_plan, order_id))
                
                # Small delay to let writer start its transaction and perform UPDATE
                await asyncio.sleep(0.3)
                
                # Then start reader
                reader_task = asyncio.create_task(self._execute_actor(state, reader_plan, order_id))
                
                results = await asyncio.gather(writer_task, reader_task, return_exceptions=True)
            elif state.payload.scenario == ScenarioType.WRITE_WRITE and len(plans) == 2:
                # WRITE_WRITE: Both writers start simultaneously to create contention
                # This tests FOR UPDATE locking behavior and serialization conflicts
                await state.log("write_write_concurrent_start", 
                    message="Both writers starting simultaneously for maximum contention")
                
                tasks = [asyncio.create_task(self._execute_actor(state, plan, order_id)) for plan in plans]
                results = await asyncio.gather(*tasks, return_exceptions=True)
            elif state.payload.scenario == ScenarioType.NON_REPEATABLE_READ and len(plans) == 2:
                # NON_REPEATABLE_READ: Reader starts first with delay, writer updates in between reads
                # This tests if the same row returns different values within one transaction
                reader_plan = plans[0]  # First actor is reader
                writer_plan = plans[1]  # Second actor is writer
                
                await state.log("non_repeatable_read_test_start",
                    message="Reader starts first, writer will update between reads")
                
                # Start reader first (it will read, delay, then read again)
                reader_task = asyncio.create_task(self._execute_actor(state, reader_plan, order_id))
                
                # Small delay to let reader perform first read
                await asyncio.sleep(0.5)
                
                # Then start writer to update the row
                writer_task = asyncio.create_task(self._execute_actor(state, writer_plan, order_id))
                
                results = await asyncio.gather(reader_task, writer_task, return_exceptions=True)
            elif state.payload.scenario == ScenarioType.PHANTOM_READ and len(plans) == 2:
                # PHANTOM_READ: Reader scans range first with delay, writer inserts in between scans
                # This tests if new rows appear in repeated range scans within one transaction
                reader_plan = plans[0]  # First actor is range reader
                writer_plan = plans[1]  # Second actor is inserter
                
                await state.log("phantom_read_test_start",
                    message="Reader scans range twice, writer will insert between scans")
                
                # Start reader first (it will scan, delay, then scan again)
                reader_task = asyncio.create_task(self._execute_actor(state, reader_plan, order_id))
                
                # Small delay to let reader perform first scan
                await asyncio.sleep(0.5)
                
                # Then start writer to insert a new row
                writer_task = asyncio.create_task(self._execute_actor(state, writer_plan, order_id))
                
                results = await asyncio.gather(reader_task, writer_task, return_exceptions=True)
            else:
                # Other scenarios: run concurrently
                tasks = [asyncio.create_task(self._execute_actor(state, plan, order_id)) for plan in plans]
                results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception) and state.status == "running":
                    state.status = "failed"
            if state.status == "running":
                state.summary = await self._collect_summary(state)
                state.mark_finished("completed")
        except asyncio.CancelledError:
            state.mark_finished("aborted")
            raise
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.exception("Orchestration run %s failed", state.id)
            await state.log("run_failed", error=str(exc))
            state.mark_finished("failed")
        finally:
            if state.finished_at is None:
                state.mark_finished(state.status)

    async def _resolve_target_order(self, requested_id: Optional[UUID]) -> Tuple[UUID, int]:
        node = self._primary_node().lower()
        dsn = self._node_dsns.get(node)
        if not dsn:
            raise RuntimeError(f"Missing DSN for node {node}")
        conn = await self._connection_factory(dsn)
        try:
            if requested_id:
                row = await conn.fetchrow(
                    "SELECT order_id, quantity FROM orders WHERE order_id = $1",
                    requested_id,
                )
                if not row:
                    raise ValueError(f"Order {requested_id} not found on primary node")
                return row["order_id"], row["quantity"]
            row = await conn.fetchrow(
                "SELECT order_id, quantity FROM orders ORDER BY updated_at DESC LIMIT 1"
            )
            if row:
                return row["order_id"], row["quantity"]
            order_id = uuid4()
            quantity = 1 if node != "node2" else self.settings.partition_rule + 1
            payload_json = json.dumps({})
            await conn.execute(
                """
                INSERT INTO orders (order_id, quantity, payload, created_at, updated_at)
                VALUES ($1, $2, $3::jsonb, NOW(), NOW())
                ON CONFLICT (order_id) DO NOTHING
                """,
                order_id,
                quantity,
                payload_json,
            )
            return order_id, quantity
        finally:
            await conn.close()

    def _prepare_plans(self, state: RunState) -> List[ActorPlan]:
        roles = state.payload.scenario.roles
        actors = state.payload.actors
        if len(actors) != len(roles):
            raise ValueError("Scenario requires exactly two actors")
        seen: set[str] = set()
        plans: List[ActorPlan] = []
        for actor, role in zip(actors, roles):
            actor_id = actor.name.strip() or role
            if actor_id in seen:
                raise ValueError("Actor names must be unique per run")
            seen.add(actor_id)
            node = actor.node.lower()
            if node not in self._node_dsns:
                raise ValueError(f"Unknown node '{actor.node}'")
            # For write role: need either new_quantity OR auto_increment
            if role == "write" and actor.new_quantity is None and not actor.auto_increment:
                raise ValueError(f"Actor {actor_id} must provide new_quantity or use auto_increment for write operations")
            plan = ActorPlan(
                actor_id=actor_id,
                node=node,
                role=role,
                isolation_level=actor.isolation_level,
                delay_seconds=max(0.0, actor.delay_seconds),
                new_quantity=actor.new_quantity,
                auto_increment=actor.auto_increment,
            )
            state.actor_levels[actor_id] = actor.isolation_level
            plans.append(plan)
        return plans

    async def _execute_actor(self, state: RunState, plan: ActorPlan, order_id: UUID) -> None:
        # Track execution time
        start_time = datetime.now(timezone.utc)
        state.client_status[plan.actor_id] = {
            "status": "running",
            "node": plan.node,
            "role": plan.role,
            "isolation_level": plan.isolation_level.sql_clause,
            "delay_seconds": plan.delay_seconds,
            "start_time": start_time.isoformat(),
        }
        if plan.auto_increment:
            state.client_status[plan.actor_id]["auto_increment"] = True
        elif plan.new_quantity is not None:
            state.client_status[plan.actor_id]["new_quantity"] = plan.new_quantity

        # Check if this is a remote node - use HTTP instead of direct DB connection
        if not self._is_local_node(plan.node):
            await self._execute_remote_actor(state, plan, order_id)
            return

        # Local node - use direct database connection
        dsn = self._node_dsns.get(plan.node)
        if not dsn:
            raise RuntimeError(f"Missing DSN for node {plan.node}")
        conn = await self._connection_factory(dsn)
        try:
            await conn.execute(
                f"BEGIN TRANSACTION ISOLATION LEVEL {plan.isolation_level.sql_clause}"
            )
            txn_start = datetime.now(timezone.utc)  # Track transaction start (after BEGIN)
            await state.log(
                "transaction_started",
                actor_id=plan.actor_id,
                node=plan.node,
                role=plan.role,
                isolation=plan.isolation_level.sql_clause,
            )
            if plan.role == "read" or plan.role == "read_range":
                details = await self._perform_read(state, conn, plan, order_id)
            elif plan.role == "insert":
                details = await self._perform_insert(state, conn, plan, order_id)
            else:
                details = await self._perform_write(state, conn, plan, order_id)
                # For READ_WRITE scenario: writer delays before commit to allow
                # reader to attempt reading uncommitted data (dirty read test)
                if state.payload.scenario == ScenarioType.READ_WRITE:
                    await state.log("write_delay_before_commit", actor_id=plan.actor_id, seconds=1.0)
                    await asyncio.sleep(1.0)  # Hold transaction open for dirty read testing
            await conn.execute("COMMIT")
            txn_end = datetime.now(timezone.utc)  # Track transaction end (after COMMIT)
            
            # Calculate execution times
            total_time = (txn_end - start_time).total_seconds()
            txn_time = (txn_end - txn_start).total_seconds()
            
            state.client_status[plan.actor_id]["status"] = "committed"
            state.client_status[plan.actor_id]["end_time"] = txn_end.isoformat()
            state.execution_times[plan.actor_id] = {
                "total_seconds": total_time,
                "transaction_seconds": txn_time,
                "delay_seconds": plan.delay_seconds,
                "net_execution_seconds": txn_time - plan.delay_seconds,
            }
            state.actor_results[plan.actor_id] = {
                "node": plan.node,
                "role": plan.role,
                "isolation_level": plan.isolation_level.sql_clause,
                "delay_seconds": plan.delay_seconds,
                "execution_time": state.execution_times[plan.actor_id],
                "details": details,
            }
        except asyncio.CancelledError:
            await conn.execute("ROLLBACK")
            end_time = datetime.now(timezone.utc)
            state.client_status[plan.actor_id]["status"] = "cancelled"
            state.client_status[plan.actor_id]["end_time"] = end_time.isoformat()
            state.execution_times[plan.actor_id] = {
                "total_seconds": (end_time - start_time).total_seconds(),
                "status": "cancelled",
            }
            raise
        except Exception as exc:
            await conn.execute("ROLLBACK")
            end_time = datetime.now(timezone.utc)
            sqlstate = getattr(exc, "sqlstate", None)
            if sqlstate == "40001":
                state.serialization_conflicts.append(plan.actor_id)
                await state.log("client_serialization_abort", actor_id=plan.actor_id, error=str(exc))
                state.client_status[plan.actor_id]["status"] = "serialization_aborted"
            else:
                await state.log("client_error", actor_id=plan.actor_id, error=str(exc))
                state.client_status[plan.actor_id]["status"] = "error"
                state.status = "failed"
            state.client_status[plan.actor_id]["end_time"] = end_time.isoformat()
            state.execution_times[plan.actor_id] = {
                "total_seconds": (end_time - start_time).total_seconds(),
                "status": "error" if sqlstate != "40001" else "serialization_aborted",
            }
            if sqlstate != "40001":
                raise
        finally:
            await conn.close()

    async def _execute_remote_actor(self, state: RunState, plan: ActorPlan, order_id: UUID) -> None:
        """Execute an actor on a remote node via HTTP API."""
        node_url = self._node_urls.get(plan.node)
        if not node_url:
            raise RuntimeError(f"No URL configured for remote node {plan.node}")
        if not self._http_client:
            raise RuntimeError("HTTP client not configured for remote node communication")

        await state.log(
            "transaction_started",
            actor_id=plan.actor_id,
            node=plan.node,
            role=plan.role,
            isolation=plan.isolation_level.sql_clause,
            remote=True,
        )

        try:
            # Call the remote node's local-transaction endpoint
            payload = {
                "order_id": str(order_id),
                "actor_id": plan.actor_id,
                "role": plan.role,
                "isolation_level": plan.isolation_level.value,
                "delay_seconds": plan.delay_seconds,
                "new_quantity": plan.new_quantity,
                "auto_increment": plan.auto_increment,
            }
            # For READ_WRITE scenario writers, add delay before commit for dirty read testing
            if state.payload.scenario == ScenarioType.READ_WRITE and plan.role == "write":
                payload["delay_before_commit"] = 1.0
            # For WRITE_WRITE scenario, add delay after lock to create contention
            if state.payload.scenario == ScenarioType.WRITE_WRITE and plan.role == "write":
                payload["delay_after_lock"] = 0.5
            url = f"{node_url}/orchestrator/local-transaction"
            result = await self._http_client.post_json(url, payload)

            # Process the result
            remote_status = result.get("status", "error")
            state.client_status[plan.actor_id]["status"] = remote_status

            if remote_status == "committed":
                details = result.get("details", {})
                state.actor_results[plan.actor_id] = {
                    "node": plan.node,
                    "role": plan.role,
                    "isolation_level": plan.isolation_level.sql_clause,
                    "delay_seconds": plan.delay_seconds,
                    "details": details,
                }
                if plan.role == "read":
                    await state.log(
                        "read_complete",
                        actor_id=plan.actor_id,
                        initial_quantity=details.get("initial_quantity"),
                        final_quantity=details.get("final_quantity"),
                    )
                else:
                    await state.log(
                        "write_complete",
                        actor_id=plan.actor_id,
                        previous_quantity=details.get("locked_quantity"),
                        committed_quantity=details.get("committed_quantity"),
                    )
            elif remote_status == "serialization_aborted":
                state.serialization_conflicts.append(plan.actor_id)
                await state.log(
                    "client_serialization_abort",
                    actor_id=plan.actor_id,
                    error=result.get("error", "Serialization conflict"),
                )
            else:
                await state.log(
                    "client_error",
                    actor_id=plan.actor_id,
                    error=result.get("error", "Remote transaction failed"),
                )
                state.status = "failed"
                raise RuntimeError(result.get("error", "Remote transaction failed"))

        except Exception as exc:
            if "serialization" not in str(exc).lower():
                await state.log("client_error", actor_id=plan.actor_id, error=str(exc))
                state.client_status[plan.actor_id]["status"] = "error"
                state.status = "failed"
            raise

    async def _perform_read(
        self,
        state: RunState,
        conn: asyncpg.Connection,
        plan: ActorPlan,
        order_id: UUID,
    ) -> Dict[str, Any]:
        # For read_range (phantom read testing): scan a range of orders
        if plan.role == "read_range":
            # First range scan
            rows_before = await conn.fetch(
                "SELECT order_id, quantity FROM orders ORDER BY quantity LIMIT 10"
            )
            count_before = len(rows_before)
            await state.log(
                "range_scan_snapshot",
                actor_id=plan.actor_id,
                count=count_before,
                rows=[{"order_id": str(r["order_id"]), "quantity": r["quantity"]} for r in rows_before],
            )
            
            if plan.delay_seconds:
                await conn.execute("SELECT pg_sleep($1)", plan.delay_seconds)
                await state.log("pg_sleep", actor_id=plan.actor_id, seconds=plan.delay_seconds)
            
            # Second range scan (should see phantom if writer inserted)
            rows_after = await conn.fetch(
                "SELECT order_id, quantity FROM orders ORDER BY quantity LIMIT 10"
            )
            count_after = len(rows_after)
            await state.log(
                "range_scan_complete",
                actor_id=plan.actor_id,
                initial_count=count_before,
                final_count=count_after,
                phantom_detected=count_after != count_before,
            )
            return {
                "initial_count": count_before,
                "final_count": count_after,
                "phantom_detected": count_after != count_before,
                "initial_rows": [{"order_id": str(r["order_id"]), "quantity": r["quantity"]} for r in rows_before],
                "final_rows": [{"order_id": str(r["order_id"]), "quantity": r["quantity"]} for r in rows_after],
            }
        
        # Standard single-row read (for non-repeatable read testing)
        snapshot = await conn.fetchrow(
            "SELECT quantity FROM orders WHERE order_id = $1 FOR SHARE",
            order_id,
        )
        qty_before = snapshot["quantity"] if snapshot else None
        await state.log(
            "read_snapshot",
            actor_id=plan.actor_id,
            quantity=qty_before,
        )
        if plan.delay_seconds:
            await conn.execute("SELECT pg_sleep($1)", plan.delay_seconds)
            await state.log("pg_sleep", actor_id=plan.actor_id, seconds=plan.delay_seconds)
        follow_up = await conn.fetchrow(
            "SELECT quantity FROM orders WHERE order_id = $1",
            order_id,
        )
        qty_after = follow_up["quantity"] if follow_up else None
        non_repeatable = qty_before != qty_after
        await state.log(
            "read_complete",
            actor_id=plan.actor_id,
            initial_quantity=qty_before,
            final_quantity=qty_after,
            non_repeatable_detected=non_repeatable,
        )
        return {
            "initial_quantity": qty_before,
            "final_quantity": qty_after,
            "non_repeatable_detected": non_repeatable,
        }

    async def _perform_insert(
        self,
        state: RunState,
        conn: asyncpg.Connection,
        plan: ActorPlan,
        order_id: UUID,
    ) -> Dict[str, Any]:
        """Insert a new order for phantom read testing."""
        # Generate a new order with a quantity value that fits in the range being scanned
        new_order_id = uuid4()
        new_quantity = plan.new_quantity if plan.new_quantity is not None else 5  # Default to middle range
        
        await state.log("insert_preparing", actor_id=plan.actor_id, new_order_id=str(new_order_id), quantity=new_quantity)
        
        if plan.delay_seconds:
            await conn.execute("SELECT pg_sleep($1)", plan.delay_seconds)
            await state.log("pg_sleep", actor_id=plan.actor_id, seconds=plan.delay_seconds)
        
        # Insert the new order
        payload_json = json.dumps({})
        await conn.execute(
            """
            INSERT INTO orders (order_id, quantity, payload, created_at, updated_at)
            VALUES ($1, $2, $3::jsonb, NOW(), NOW())
            ON CONFLICT (order_id) DO NOTHING
            """,
            new_order_id,
            new_quantity,
            payload_json,
        )
        
        # Write to op_log for replication
        origin_node = self.settings.node_name
        lamport_value = await lamport_utils.next_lamport(conn, origin_node)
        op_payload = {"quantity": new_quantity, "payload": {}}
        op_payload_json = json.dumps(op_payload)
        await conn.execute(
            """
            INSERT INTO op_log (
                op_id, origin_node, op_type, table_name, row_id, payload,
                ts, lamport, applied, applied_ts
            ) VALUES ($1,$2,$3,$4,$5,$6::jsonb,NOW(),$7,false,NULL)
            ON CONFLICT (op_id) DO NOTHING
            """,
            uuid4(),
            origin_node,
            "upsert",
            "orders",
            new_order_id,
            op_payload_json,
            lamport_value,
        )
        
        await state.log(
            "insert_complete",
            actor_id=plan.actor_id,
            new_order_id=str(new_order_id),
            quantity=new_quantity,
        )
        return {
            "inserted_order_id": str(new_order_id),
            "quantity": new_quantity,
        }

    async def _perform_write(
        self,
        state: RunState,
        conn: asyncpg.Connection,
        plan: ActorPlan,
        order_id: UUID,
    ) -> Dict[str, Any]:
        row = await conn.fetchrow(
            "SELECT quantity, payload FROM orders WHERE order_id = $1 FOR UPDATE",
            order_id,
        )
        current_qty = row["quantity"] if row else None
        current_payload = row["payload"] if row else None
        await state.log("write_locked", actor_id=plan.actor_id, quantity=current_qty)
        
        # For WRITE_WRITE: add delay after getting lock to let other writer queue up
        # This creates contention and demonstrates serialization behavior
        if state.payload.scenario == ScenarioType.WRITE_WRITE:
            await asyncio.sleep(0.5)  # Hold lock to create contention
        
        if plan.delay_seconds:
            await conn.execute("SELECT pg_sleep($1)", plan.delay_seconds)
            await state.log("pg_sleep", actor_id=plan.actor_id, seconds=plan.delay_seconds)
        
        # Determine the new quantity value
        if plan.auto_increment:
            # Auto-increment: add 1 to current quantity
            final_quantity = (current_qty or 0) + 1
        else:
            final_quantity = plan.new_quantity
        
        await conn.execute(
            "UPDATE orders SET quantity = $2, updated_at = NOW() WHERE order_id = $1",
            order_id,
            final_quantity,
        )
        
        # Write to op_log for replication
        origin_node = self.settings.node_name
        lamport_value = await lamport_utils.next_lamport(conn, origin_node)
        op_payload = {"quantity": final_quantity, "payload": current_payload}
        op_payload_json = json.dumps(op_payload)
        await conn.execute(
            """
            INSERT INTO op_log (
                op_id, origin_node, op_type, table_name, row_id, payload,
                ts, lamport, applied, applied_ts
            ) VALUES ($1,$2,$3,$4,$5,$6::jsonb,NOW(),$7,false,NULL)
            ON CONFLICT (op_id) DO NOTHING
            """,
            uuid4(),
            origin_node,
            "upsert",
            "orders",
            order_id,
            op_payload_json,
            lamport_value,
        )
        
        await state.log(
            "write_complete",
            actor_id=plan.actor_id,
            previous_quantity=current_qty,
            committed_quantity=final_quantity,
        )
        return {
            "locked_quantity": current_qty,
            "committed_quantity": final_quantity,
        }

    async def _collect_summary(self, state: RunState) -> Dict[str, Any]:
        order_id = state.order_id
        if order_id is None:
            return {}
        final_states: Dict[str, Any] = {}
        for node, dsn in self._node_dsns.items():
            if not dsn:
                final_states[node] = {"available": False}
                continue
            final_states[node] = await self._fetch_node_snapshot(dsn, order_id)
        primary_state = final_states.get(self._primary_node().lower(), {})
        final_quantity = primary_state.get("quantity") if isinstance(primary_state, dict) else None
        delta = None
        if final_quantity is not None and state.initial_quantity is not None:
            delta = final_quantity - state.initial_quantity
        isolation_overview = {
            actor_id: level.sql_clause
            for actor_id, level in state.actor_levels.items()
        }
        note = next((level.note for level in state.actor_levels.values() if level.note), None)
        
        # Generate verdict based on scenario and results
        verdict = None
        if state.payload.scenario == ScenarioType.WRITE_WRITE:
            # For WRITE_WRITE: analyze if both increments succeeded
            committed_count = sum(
                1 for info in state.client_status.values() 
                if info.get("status") == "committed"
            )
            conflict_count = len(state.serialization_conflicts)
            
            if committed_count == 2 and conflict_count == 0:
                if delta == 2:
                    verdict = "✅ Both writers committed successfully. Quantity increased by 2 (no lost update). FOR UPDATE locking prevented conflicts."
                elif delta == 1:
                    verdict = "⚠️ Both writers committed but only +1 delta. Possible race condition or same value written."
                else:
                    verdict = f"Both writers committed. Delta: {delta}"
            elif committed_count == 1 and conflict_count == 1:
                verdict = "✅ One writer succeeded, one aborted (serialization conflict). This is expected behavior for REPEATABLE READ/SERIALIZABLE isolation."
            elif conflict_count > 0:
                verdict = f"⚠️ Serialization conflicts detected: {conflict_count}. {committed_count} writer(s) committed."
            else:
                verdict = f"Writers status: {committed_count} committed, {conflict_count} conflicts."
        elif state.payload.scenario == ScenarioType.NON_REPEATABLE_READ:
            # Check if non-repeatable read was detected
            for actor_id, result in state.actor_results.items():
                if result.get("role") == "read":
                    details = result.get("details", {})
                    if details.get("non_repeatable_detected"):
                        verdict = "⚠️ Non-repeatable read detected! Same row returned different values within transaction."
                    else:
                        verdict = "✅ No non-repeatable read. Isolation level prevented the anomaly."
        elif state.payload.scenario == ScenarioType.PHANTOM_READ:
            # Check if phantom read was detected
            for actor_id, result in state.actor_results.items():
                if result.get("role") == "read_range":
                    details = result.get("details", {})
                    if details.get("phantom_detected"):
                        verdict = f"⚠️ Phantom read detected! Row count changed from {details.get('initial_count')} to {details.get('final_count')}."
                    else:
                        verdict = "✅ No phantom read. Isolation level prevented the anomaly."
        
        return {
            "order_id": str(order_id),
            "initial_quantity": state.initial_quantity,
            "final_quantity": final_quantity,
            "delta": delta,
            "final_states": final_states,
            "actor_results": state.actor_results,
            "isolation_overview": isolation_overview,
            "read_uncommitted_note": note,
            "serialization_conflicts": state.serialization_conflicts,
            "execution_times": state.execution_times,
            "verdict": verdict,
            "replication_note": "Node snapshots reflect latest pull at query time; minor lag is expected.",
        }

    async def _fetch_node_snapshot(self, dsn: str, order_id: UUID) -> Dict[str, Any]:
        conn = await self._connection_factory(dsn)
        try:
            row = await conn.fetchrow(
                "SELECT order_id, quantity, payload, updated_at FROM orders WHERE order_id = $1",
                order_id,
            )
            if not row:
                return {"present": False}
            return {
                "present": True,
                "quantity": row.get("quantity"),
                "payload": row.get("payload"),
                "updated_at": row.get("updated_at").isoformat() if row.get("updated_at") else None,
            }
        finally:
            await conn.close()

    @staticmethod
    def _record_to_dict(record: Any) -> Dict[str, Any]:
        if hasattr(record, "items"):
            return dict(record.items())
        if isinstance(record, dict):
            return record
        return {"value": str(record)}
