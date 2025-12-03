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
    NON_REPEATABLE_READ = "NON_REPEATABLE_READ"
    PHANTOM_READ = "PHANTOM_READ"

    @property
    def roles(self) -> Tuple[str, str]:
        mapping = {
            ScenarioType.READ_READ: ("read", "read"),
            ScenarioType.READ_WRITE: ("write", "read"),  # Writer first (on node_x), Reader second (on node_y)
            ScenarioType.WRITE_WRITE: ("write", "write"),
            ScenarioType.NON_REPEATABLE_READ: ("read", "write"),  # Reader first, Writer updates during
            ScenarioType.PHANTOM_READ: ("read", "write"),  # Reader with COUNT/SELECT_RANGE, Writer inserts
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
        # Timing infrastructure
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.actor_timings: Dict[str, Dict[str, float]] = {}  # actor_id -> {total_duration_ms, sleep_time_ms, execution_time_ms}

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

    async def _check_node_available(self, node: str) -> bool:
        """Check if a node is available (not disabled and reachable)."""
        node_lower = node.lower()
        
        # For local node, check the disabled flag directly
        if self._is_local_node(node_lower):
            from .routes.admin import is_node_disabled
            return not is_node_disabled()
        
        # For remote nodes, try to reach their health endpoint
        node_url = self._node_urls.get(node_lower)
        if not node_url:
            return False
        
        if not self._http_client:
            return False
        
        try:
            result = await self._http_client.get_json(f"{node_url}/health", timeout=3.0)
            return result.get("status") == "ok"
        except Exception:
            return False

    async def _get_available_nodes(self) -> List[str]:
        """Get list of currently available nodes."""
        available = []
        for node in self._node_dsns.keys():
            if await self._check_node_available(node):
                available.append(node)
        return available

    async def _get_available_primary(self) -> str:
        """Get an available primary node, falling back if default is unavailable."""
        default_primary = self._primary_node().lower()
        
        # First try the default primary
        if await self._check_node_available(default_primary):
            return default_primary
        
        # If default primary is unavailable, try other nodes
        # Prefer local node if it's not the default primary
        local_node = self.settings.node_name.lower()
        if local_node != default_primary and await self._check_node_available(local_node):
            LOGGER.warning(f"Primary {default_primary} unavailable, falling back to local node {local_node}")
            return local_node
        
        # Try any other available node
        for node in self._node_dsns.keys():
            if node != default_primary and await self._check_node_available(node):
                LOGGER.warning(f"Primary {default_primary} unavailable, falling back to {node}")
                return node
        
        # Last resort: return the default even if unavailable (will fail later with clear error)
        return default_primary

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
            
            # For READ_WRITE scenario: writer executes first, readers follow
            # This allows testing dirty reads (readers see uncommitted) or 
            # committed reads (readers see after commit)
            if state.payload.scenario == ScenarioType.READ_WRITE:
                writer_plan = plans[0]  # First actor is writer
                reader_plans = plans[1:]  # Remaining actors are readers
                
                await state.log("read_write_start",
                    message=f"1 writer + {len(reader_plans)} reader(s) starting")
                
                # Start writer first
                writer_task = asyncio.create_task(self._execute_actor(state, writer_plan, order_id))
                
                # Small delay to let writer start its transaction and perform UPDATE
                await asyncio.sleep(0.3)
                
                # Then start all readers
                reader_tasks = [asyncio.create_task(self._execute_actor(state, plan, order_id)) for plan in reader_plans]
                
                results = await asyncio.gather(writer_task, *reader_tasks, return_exceptions=True)
            elif state.payload.scenario == ScenarioType.WRITE_WRITE:
                # WRITE_WRITE: All writers start simultaneously to create contention
                # This tests FOR UPDATE locking behavior and serialization conflicts
                await state.log("write_write_concurrent_start", 
                    message=f"{len(plans)} writers starting simultaneously for maximum contention")
                
                tasks = [asyncio.create_task(self._execute_actor(state, plan, order_id)) for plan in plans]
                results = await asyncio.gather(*tasks, return_exceptions=True)
            elif state.payload.scenario == ScenarioType.READ_READ:
                # READ_READ: All readers start simultaneously
                await state.log("read_read_concurrent_start",
                    message=f"{len(plans)} readers starting simultaneously to test snapshot isolation")
                
                tasks = [asyncio.create_task(self._execute_actor(state, plan, order_id)) for plan in plans]
                results = await asyncio.gather(*tasks, return_exceptions=True)
            elif state.payload.scenario == ScenarioType.NON_REPEATABLE_READ:
                # NON_REPEATABLE_READ: Reader starts first with sleep, writers update during sleep
                reader_plan = plans[0]  # First actor is reader
                writer_plans = plans[1:]  # Remaining actors are writers
                
                await state.log("non_repeatable_read_start",
                    message=f"Reader starting first, {len(writer_plans)} writer(s) will update during reader's sleep")
                
                # Start reader first
                reader_task = asyncio.create_task(self._execute_actor(state, reader_plan, order_id))
                
                # Delay to let reader perform first SELECT and start sleeping
                await asyncio.sleep(0.5)
                
                # Start all writers to update during reader's sleep
                writer_tasks = [asyncio.create_task(self._execute_actor(state, plan, order_id)) for plan in writer_plans]
                
                results = await asyncio.gather(reader_task, *writer_tasks, return_exceptions=True)
            elif state.payload.scenario == ScenarioType.PHANTOM_READ:
                # PHANTOM_READ: Reader performs COUNT/range queries, writers modify during sleep
                # Note: Current implementation uses UPDATE, not INSERT (limitation)
                reader_plan = plans[0]  # First actor is reader
                writer_plans = plans[1:]  # Remaining actors are writers
                
                await state.log("phantom_read_start",
                    message=f"Reader starting first with range queries, {len(writer_plans)} writer(s) will modify during sleep")
                
                # Start reader first
                reader_task = asyncio.create_task(self._execute_actor(state, reader_plan, order_id))
                
                # Delay to let reader perform first queries and start sleeping
                await asyncio.sleep(0.5)
                
                # Start all writers to modify during reader's sleep
                writer_tasks = [asyncio.create_task(self._execute_actor(state, plan, order_id)) for plan in writer_plans]
                
                results = await asyncio.gather(reader_task, *writer_tasks, return_exceptions=True)
                
                # Cleanup: Revert the quantity changes made by writers
                await self._cleanup_phantom_read(state, order_id, len(writer_plans))
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
        node = await self._get_available_primary()
        dsn = self._node_dsns.get(node)
        if not dsn:
            raise RuntimeError(f"Missing DSN for node {node}")
        try:
            conn = await self._connection_factory(dsn)
        except Exception as e:
            LOGGER.warning(f"Failed to connect to {node}: {e}, trying fallback")
            # Try other nodes
            for fallback_node in self._node_dsns.keys():
                if fallback_node != node:
                    fallback_dsn = self._node_dsns.get(fallback_node)
                    if fallback_dsn:
                        try:
                            conn = await self._connection_factory(fallback_dsn)
                            node = fallback_node
                            break
                        except Exception:
                            continue
            else:
                raise RuntimeError(f"No available database nodes: {e}")
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
        
        # For READ_READ and WRITE_WRITE, allow N actors (all same role)
        if state.payload.scenario in (ScenarioType.READ_READ, ScenarioType.WRITE_WRITE):
            expected_role = roles[0]  # All actors have same role
            # Validate all actors have the expected role
            # (in this case, we'll assign the role based on scenario)
        else:
            # For other scenarios, enforce exact count
            if len(actors) != len(roles):
                raise ValueError(f"Scenario {state.payload.scenario.value} requires exactly {len(roles)} actors")
        
        seen: set[str] = set()
        plans: List[ActorPlan] = []
        
        for i, actor in enumerate(actors):
            # Determine role based on scenario
            if state.payload.scenario == ScenarioType.READ_READ:
                role = "read"
            elif state.payload.scenario == ScenarioType.WRITE_WRITE:
                role = "write"
            else:
                # For other scenarios, use roles from scenario definition
                role = roles[i] if i < len(roles) else roles[-1]
            
            actor_id = actor.name.strip() or f"{role}_{i}"
            if actor_id in seen:
                raise ValueError("Actor names must be unique per run")
            seen.add(actor_id)
            node = actor.node.lower()
            if node not in self._node_dsns:
                raise ValueError(f"Unknown node '{actor.node}'")
            # For write role: need either new_quantity OR auto_increment
            # For NON_REPEATABLE_READ and PHANTOM_READ, default to auto_increment if not specified
            auto_increment_val = actor.auto_increment
            new_quantity_val = actor.new_quantity
            
            if role == "write" and new_quantity_val is None and not auto_increment_val:
                if state.payload.scenario in (ScenarioType.NON_REPEATABLE_READ, ScenarioType.PHANTOM_READ):
                    # Default to auto_increment for these scenarios
                    auto_increment_val = True
                else:
                    raise ValueError(f"Actor {actor_id} must provide new_quantity or use auto_increment for write operations")
            
            plan = ActorPlan(
                actor_id=actor_id,
                node=node,
                role=role,
                isolation_level=actor.isolation_level,
                delay_seconds=max(0.0, actor.delay_seconds),
                new_quantity=new_quantity_val,
                auto_increment=auto_increment_val,
            )
            state.actor_levels[actor_id] = actor.isolation_level
            plans.append(plan)
        return plans

    async def _execute_actor(self, state: RunState, plan: ActorPlan, order_id: UUID) -> None:
        import time
        
        start_time = time.perf_counter()
        sleep_time_ms = 0.0
        
        state.client_status[plan.actor_id] = {
            "status": "running",
            "node": plan.node,
            "role": plan.role,
            "isolation_level": plan.isolation_level.sql_clause,
            "delay_seconds": plan.delay_seconds,
        }
        if plan.auto_increment:
            state.client_status[plan.actor_id]["auto_increment"] = True
        elif plan.new_quantity is not None:
            state.client_status[plan.actor_id]["new_quantity"] = plan.new_quantity

        # Check if this is a remote node - use HTTP instead of direct DB connection
        if not self._is_local_node(plan.node):
            await self._execute_remote_actor(state, plan, order_id)
            # For remote execution, calculate timing
            end_time = time.perf_counter()
            total_duration_ms = (end_time - start_time) * 1000
            # Estimate sleep time based on delay_seconds
            if plan.delay_seconds:
                sleep_time_ms = plan.delay_seconds * 1000
            state.actor_timings[plan.actor_id] = {
                "total_duration_ms": total_duration_ms,
                "sleep_time_ms": sleep_time_ms,
                "execution_time_ms": total_duration_ms - sleep_time_ms,
            }
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
            await state.log(
                "transaction_started",
                actor_id=plan.actor_id,
                node=plan.node,
                role=plan.role,
                isolation=plan.isolation_level.sql_clause,
            )
            if plan.role == "read":
                details = await self._perform_read(state, conn, plan, order_id)
                # Track sleep time if delay was used
                if plan.delay_seconds:
                    sleep_time_ms = plan.delay_seconds * 1000
            else:
                details = await self._perform_write(state, conn, plan, order_id)
                # For READ_WRITE scenario: writer delays before commit to allow
                # reader to attempt reading uncommitted data (dirty read test)
                if state.payload.scenario == ScenarioType.READ_WRITE:
                    await state.log("write_delay_before_commit", actor_id=plan.actor_id, seconds=1.0)
                    await asyncio.sleep(1.0)  # Hold transaction open for dirty read testing
                    sleep_time_ms += 1000  # Add commit delay to sleep time
            await conn.execute("COMMIT")
            state.client_status[plan.actor_id]["status"] = "committed"
            state.actor_results[plan.actor_id] = {
                "node": plan.node,
                "role": plan.role,
                "isolation_level": plan.isolation_level.sql_clause,
                "delay_seconds": plan.delay_seconds,
                "details": details,
            }
            
            # Calculate and store timing
            end_time = time.perf_counter()
            total_duration_ms = (end_time - start_time) * 1000
            state.actor_timings[plan.actor_id] = {
                "total_duration_ms": total_duration_ms,
                "sleep_time_ms": sleep_time_ms,
                "execution_time_ms": total_duration_ms - sleep_time_ms,
            }
            
        except asyncio.CancelledError:
            await conn.execute("ROLLBACK")
            state.client_status[plan.actor_id]["status"] = "cancelled"
            raise
        except Exception as exc:
            await conn.execute("ROLLBACK")
            sqlstate = getattr(exc, "sqlstate", None)
            if sqlstate == "40001":
                state.serialization_conflicts.append(plan.actor_id)
                await state.log("client_serialization_abort", actor_id=plan.actor_id, error=str(exc))
                state.client_status[plan.actor_id]["status"] = "serialization_aborted"
            else:
                await state.log("client_error", actor_id=plan.actor_id, error=str(exc))
                state.client_status[plan.actor_id]["status"] = "error"
                state.status = "failed"
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

        # Check node availability first
        if not await self._check_node_available(plan.node):
            await state.log(
                "node_unavailable",
                actor_id=plan.actor_id,
                node=plan.node,
                message=f"Node {plan.node} is unavailable or disabled",
            )
            state.client_status[plan.actor_id]["status"] = "node_unavailable"
            state.client_status[plan.actor_id]["error"] = f"Node {plan.node} is unavailable"
            raise RuntimeError(f"Node {plan.node} is unavailable or disabled")

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
                "scenario": state.payload.scenario.value,
            }
            # For READ_WRITE scenario writers, add delay before commit for dirty read testing
            if state.payload.scenario == ScenarioType.READ_WRITE and plan.role == "write":
                payload["delay_before_commit"] = 1.0
            # For WRITE_WRITE scenario, add delay after lock to create contention
            if state.payload.scenario == ScenarioType.WRITE_WRITE and plan.role == "write":
                payload["delay_after_lock"] = 0.5
            # For NON_REPEATABLE_READ and PHANTOM_READ, no special delays needed (using delay_seconds)
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
        # For NON_REPEATABLE_READ and PHANTOM_READ: don't use FOR SHARE
        # This allows writers to modify data during the reader's sleep, enabling anomaly detection
        # For READ_WRITE: use FOR SHARE to demonstrate read locking behavior
        # For READ_READ: use simple SELECT (no locking overhead)
        use_for_share = (
            state.payload.scenario == ScenarioType.READ_WRITE
        )
        
        if use_for_share:
            snapshot = await conn.fetchrow(
                "SELECT quantity FROM orders WHERE order_id = $1 FOR SHARE",
                order_id,
            )
        else:
            snapshot = await conn.fetchrow(
                "SELECT quantity FROM orders WHERE order_id = $1",
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
        await state.log(
            "read_complete",
            actor_id=plan.actor_id,
            initial_quantity=qty_before,
            final_quantity=qty_after,
        )
        return {"initial_quantity": qty_before, "final_quantity": qty_after}

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

    async def _cleanup_phantom_read(
        self,
        state: RunState,
        order_id: int,
        num_writers: int,
    ) -> None:
        """
        Cleanup method for PHANTOM_READ scenarios to restore original quantity.
        Reverts the increments made by writers during the test.
        """
        primary = self._primary_node().lower()
        dsn = self._node_dsns.get(primary)
        if not dsn:
            await state.log("cleanup_skip", reason="Primary node unavailable")
            return

        await state.log(
            "cleanup_start",
            order_id=order_id,
            num_increments=num_writers,
        )

        conn = await asyncpg.connect(dsn)
        try:
            # Calculate original quantity by subtracting all writer increments
            await conn.execute(
                """
                UPDATE orders
                SET quantity = quantity - $1
                WHERE order_id = $2
                """,
                num_writers,
                order_id,
            )
            
            # Verify the cleanup
            result = await conn.fetchrow(
                "SELECT quantity FROM orders WHERE order_id = $1",
                order_id,
            )
            restored_qty = result["quantity"] if result else None
            
            await state.log(
                "cleanup_complete",
                order_id=order_id,
                restored_quantity=restored_qty,
            )
        finally:
            await conn.close()

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
            # For WRITE_WRITE: analyze if increments succeeded
            committed_count = sum(
                1 for info in state.client_status.values() 
                if info.get("status") == "committed"
            )
            conflict_count = len(state.serialization_conflicts)
            total_writers = sum(1 for info in state.client_status.values() if info.get("role") == "write")
            
            if committed_count == total_writers and conflict_count == 0:
                if delta == total_writers:
                    verdict = f"✅ All {total_writers} writers committed successfully. Quantity increased by {delta} (no lost update). FOR UPDATE locking prevented conflicts."
                else:
                    verdict = f"⚠️ All {total_writers} writers committed but delta is {delta}. Expected {total_writers}."
            elif committed_count > 0 and conflict_count > 0:
                if delta == committed_count:
                    verdict = f"✅ {committed_count} writer(s) succeeded, {conflict_count} aborted (serialization conflict). Delta matches committed count. Expected behavior for REPEATABLE READ/SERIALIZABLE."
                else:
                    verdict = f"⚠️ {committed_count} writer(s) committed, {conflict_count} conflicts. Delta: {delta} (expected {committed_count})."
            elif conflict_count > 0:
                verdict = f"⚠️ Serialization conflicts detected: {conflict_count}. {committed_count} writer(s) committed."
            else:
                verdict = f"Writers status: {committed_count}/{total_writers} committed, {conflict_count} conflicts. Delta: {delta}"
        
        # Calculate timing metrics
        timing_metrics = self._calculate_timing_metrics(state)
        
        # Detect anomalies
        anomalies = self._detect_anomalies(state)
        
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
            "verdict": verdict,
            "timing_metrics": timing_metrics,
            "anomalies": anomalies,
            "replication_note": "Node snapshots reflect latest pull at query time; minor lag is expected.",
        }
    
    def _calculate_timing_metrics(self, state: RunState) -> Dict[str, Any]:
        """Calculate aggregate and per-actor timing metrics."""
        if not state.actor_timings:
            return {}
        
        # Calculate aggregate metrics
        total_durations = [t["total_duration_ms"] for t in state.actor_timings.values()]
        sleep_times = [t["sleep_time_ms"] for t in state.actor_timings.values()]
        execution_times = [t["execution_time_ms"] for t in state.actor_timings.values()]
        
        avg_total = sum(total_durations) / len(total_durations) if total_durations else 0
        avg_sleep = sum(sleep_times) / len(sleep_times) if sleep_times else 0
        avg_exec = sum(execution_times) / len(execution_times) if execution_times else 0
        
        # Build per-actor breakdown
        per_actor = {}
        for actor_id, timing in state.actor_timings.items():
            per_actor[actor_id] = {
                "total_duration_ms": round(timing["total_duration_ms"], 2),
                "sleep_time_ms": round(timing["sleep_time_ms"], 2),
                "execution_time_ms": round(timing["execution_time_ms"], 2),
            }
        
        return {
            "avg_total_duration_ms": round(avg_total, 2),
            "avg_sleep_time_ms": round(avg_sleep, 2),
            "avg_execution_time_ms": round(avg_exec, 2),
            "per_actor": per_actor,
        }
    
    def _detect_anomalies(self, state: RunState) -> Dict[str, Any]:
        """Detect concurrency anomalies based on transaction logs and results."""
        anomalies = {
            "dirty_read": self._check_dirty_read(state),
            "non_repeatable_read": self._check_non_repeatable_read(state),
            "phantom_read": self._check_phantom_read(state),
            "lost_update": self._check_lost_update(state),
        }
        return anomalies
    
    def _check_dirty_read(self, state: RunState) -> Dict[str, Any]:
        """Check if a dirty read occurred (reading uncommitted data)."""
        # Dirty reads can only occur in READ UNCOMMITTED isolation level
        # Look for readers that saw intermediate values from uncommitted transactions
        
        occurred = False
        evidence = []
        
        for actor_id, result in state.actor_results.items():
            if result.get("role") == "read":
                details = result.get("details", {})
                initial = details.get("initial_quantity")
                final = details.get("final_quantity")
                
                # If reader saw different values and a writer was active, potential dirty read
                if initial != final:
                    # Check if there was a concurrent writer
                    writers = [a for a, r in state.actor_results.items() if r.get("role") == "write"]
                    if writers:
                        occurred = True
                        evidence.append({
                            "reader": actor_id,
                            "saw_initial": initial,
                            "saw_final": final,
                            "concurrent_writers": writers
                        })
        
        return {
            "occurred": occurred,
            "prevented": not occurred,
            "evidence": evidence,
            "description": "Reader saw uncommitted data from another transaction"
        }
    
    def _check_non_repeatable_read(self, state: RunState) -> Dict[str, Any]:
        """Check if a non-repeatable read occurred (same query, different results)."""
        occurred = False
        evidence = []
        
        for actor_id, result in state.actor_results.items():
            if result.get("role") == "read":
                details = result.get("details", {})
                initial = details.get("initial_quantity")
                final = details.get("final_quantity")
                
                # Non-repeatable read: same row queried twice, different values
                if initial is not None and final is not None and initial != final:
                    occurred = True
                    evidence.append({
                        "reader": actor_id,
                        "first_read": initial,
                        "second_read": final,
                        "difference": final - initial if isinstance(final, (int, float)) and isinstance(initial, (int, float)) else None
                    })
        
        return {
            "occurred": occurred,
            "prevented": not occurred,
            "evidence": evidence,
            "description": "Reader saw different values when querying the same row twice"
        }
    
    def _check_phantom_read(self, state: RunState) -> Dict[str, Any]:
        """Check if a phantom read occurred (range query saw new rows)."""
        # Note: Current implementation uses UPDATE not INSERT, so true phantom detection is limited
        # We detect if the writer modified data that would affect a range query
        
        occurred = False
        evidence = []
        
        # For PHANTOM_READ scenario, check if writer changed data during reader's transaction
        if state.payload.scenario == ScenarioType.PHANTOM_READ:
            readers = [(aid, r) for aid, r in state.actor_results.items() if r.get("role") == "read"]
            writers = [(aid, r) for aid, r in state.actor_results.items() if r.get("role") == "write"]
            
            for reader_id, reader_result in readers:
                reader_details = reader_result.get("details", {})
                initial = reader_details.get("initial_quantity")
                final = reader_details.get("final_quantity")
                
                # If reader saw changes (phantom would be new rows, but we detect value changes)
                if initial != final and writers:
                    occurred = True
                    evidence.append({
                        "reader": reader_id,
                        "initial_result": initial,
                        "second_result": final,
                        "note": "Value changed during transaction (actual phantom requires INSERT)"
                    })
        
        return {
            "occurred": occurred,
            "prevented": not occurred,
            "evidence": evidence,
            "description": "Reader saw different results in range query (phantom rows)"
        }
    
    def _check_lost_update(self, state: RunState) -> Dict[str, Any]:
        """Check if a lost update occurred (concurrent writes, one overwrites another)."""
        occurred = False
        evidence = []
        
        # Lost update detection for WRITE_WRITE scenario
        if state.payload.scenario == ScenarioType.WRITE_WRITE:
            writers = [(aid, r) for aid, r in state.actor_results.items() if r.get("role") == "write"]
            
            # Count committed writers
            committed_writers = [w for w in writers if state.client_status.get(w[0], {}).get("status") == "committed"]
            num_committed = len(committed_writers)
            expected_delta = num_committed  # Each committed writer should add 1
            
            if num_committed >= 2:
                # Check the actual delta
                delta = None
                if state.summary:
                    delta = state.summary.get("delta")
                elif hasattr(state, 'initial_quantity'):
                    # Calculate from available data
                    for node_snapshot in state.summary.get("final_states", {}).values() if state.summary else []:
                        if isinstance(node_snapshot, dict) and node_snapshot.get("present"):
                            final_qty = node_snapshot.get("quantity")
                            if final_qty is not None and state.initial_quantity is not None:
                                delta = final_qty - state.initial_quantity
                                break
                
                # Lost update if delta doesn't match number of committed writers
                if delta is not None and delta < expected_delta:
                    occurred = True
                    evidence.append({
                        "writers": [w[0] for w in committed_writers],
                        "expected_delta": expected_delta,
                        "actual_delta": delta,
                        "note": f"{num_committed} writers committed but only {delta} increment(s) applied"
                    })
        
        return {
            "occurred": occurred,
            "prevented": not occurred,
            "evidence": evidence,
            "description": "One transaction's update was lost due to concurrent modification"
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
