"""Transaction orchestrator for concurrent scenario execution."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple
from uuid import UUID, uuid4

import asyncpg

from .config import Settings

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


@dataclass
class StatementPlan:
	"""Represents a single SQL statement within a client script."""

	sql: str
	params: Tuple[Any, ...] = field(default_factory=tuple)
	delay_after: float = 0.0
	description: Optional[str] = None


@dataclass
class ClientPlan:
	client_id: str
	node: str
	role: str
	statements: List[StatementPlan]


@dataclass
class CustomClientScript:
	node: str
	statements: List[StatementPlan]


@dataclass
class OrchestrationInput:
	scenario: str
	isolation_level: IsolationLevel
	parallel_clients: int
	custom_transactions: Optional[List[CustomClientScript]] = None


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
			"scenario": self.payload.scenario,
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
	"""Coordinates concurrent SQL scripts across nodes."""

	def __init__(
		self,
		settings: Settings,
		promoted_flag: Callable[[], bool],
		connection_factory: Optional[Callable[[str], Awaitable[asyncpg.Connection]]] = None,
	):
		self.settings = settings
		self._promoted_flag = promoted_flag
		self._runs: Dict[str, RunState] = {}
		self._run_lock = asyncio.Lock()
		self._connection_factory = connection_factory or (lambda dsn: asyncpg.connect(dsn=dsn))
		self._node_dsns = self._build_node_dsn_map()

	def _build_node_dsn_map(self) -> Dict[str, Optional[str]]:
		mapping = {
			"node0": self.settings.node0_dsn or self.settings.database_dsn,
			"node1": self.settings.node1_dsn,
			"node2": self.settings.node2_dsn,
		}
		local_key = self.settings.node_name.lower()
		mapping[local_key] = self.settings.database_dsn
		return mapping

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
			order_id, quantity = await self._ensure_target_order()
			state.order_id = order_id
			state.initial_quantity = quantity
			plans = self._build_plans(state, order_id)
			await state.log("scenario_compiled", order_id=str(order_id), clients=len(plans))
			tasks = [asyncio.create_task(self._execute_client(state, plan)) for plan in plans]
			results = await asyncio.gather(*tasks, return_exceptions=True)
			for idx, result in enumerate(results):
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

	async def _ensure_target_order(self) -> Tuple[UUID, int]:
		node = self._primary_node().lower()
		dsn = self._node_dsns.get(node)
		if not dsn:
			raise RuntimeError(f"Missing DSN for node {node}")
	conn = await self._connection_factory(dsn)
	try:
		row = await conn.fetchrow(
			"SELECT order_id, quantity FROM orders ORDER BY updated_at DESC LIMIT 1"
		)
		if row:
			return row["order_id"], row["quantity"]
		order_id = uuid4()
		quantity = 1 if node != "node2" else self.settings.partition_rule + 1
		# Convert empty dict to JSON string for JSONB column
		import json
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
		await conn.close()	def _build_plans(self, state: RunState, order_id: UUID) -> List[ClientPlan]:
		scenario = state.payload.scenario
		count = max(1, state.payload.parallel_clients)
		if scenario == "Case1_readers_only":
			return self._case_readers_only(order_id, count)
		if scenario == "Case2_writer_readers":
			return self._case_writer_readers(order_id, count)
		if scenario == "Case3_concurrent_writers":
			return self._case_concurrent_writers(order_id, count)
		if scenario == "custom" and state.payload.custom_transactions:
			return [
				ClientPlan(
					client_id=f"custom-{idx}",
					node=script.node,
					role="custom",
					statements=script.statements,
				)
				for idx, script in enumerate(state.payload.custom_transactions)
			]
		raise ValueError(f"Unsupported scenario {scenario}")

	def _case_readers_only(self, order_id: UUID, count: int) -> List[ClientPlan]:
		plans: List[ClientPlan] = []
		node = self._primary_node().lower()
		for idx in range(count):
			statements = [
				StatementPlan(
					sql="SELECT order_id, quantity, payload FROM orders WHERE order_id = $1",
					params=(order_id,),
					delay_after=0.2,
					description="reader_snapshot",
				),
				StatementPlan(
					sql="SELECT order_id, quantity, payload FROM orders WHERE order_id = $1",
					params=(order_id,),
					description="reader_followup",
				),
			]
			plans.append(ClientPlan(client_id=f"reader-{idx+1}", node=node, role="reader", statements=statements))
		return plans

	def _case_writer_readers(self, order_id: UUID, count: int) -> List[ClientPlan]:
		node = self._primary_node().lower()
		plans: List[ClientPlan] = []
		writer_statements = [
			StatementPlan(
				sql="SELECT quantity FROM orders WHERE order_id = $1",
				params=(order_id,),
				delay_after=0.1,
				description="writer_initial_read",
			),
			StatementPlan(
				sql="UPDATE orders SET quantity = quantity + 1 WHERE order_id = $1",
				params=(order_id,),
				delay_after=0.2,
				description="writer_increment",
			),
			StatementPlan(
				sql="SELECT quantity FROM orders WHERE order_id = $1",
				params=(order_id,),
				description="writer_commit_view",
			),
		]
		plans.append(ClientPlan("writer-1", node, "writer", writer_statements))
		for idx in range(max(1, count - 1)):
			reader_statements = [
				StatementPlan(
					sql="SELECT quantity FROM orders WHERE order_id = $1",
					params=(order_id,),
					delay_after=0.15 * (idx + 1),
					description="reader_probe",
				),
				StatementPlan(
					sql="SELECT quantity FROM orders WHERE order_id = $1",
					params=(order_id,),
					description="reader_final",
				),
			]
			plans.append(ClientPlan(f"reader-{idx+1}", node, "reader", reader_statements))
		return plans

	def _case_concurrent_writers(self, order_id: UUID, count: int) -> List[ClientPlan]:
		node = self._primary_node().lower()
		plans: List[ClientPlan] = []
		for idx in range(count):
			increment = idx + 1
			statements = [
				StatementPlan(
					sql="SELECT quantity FROM orders WHERE order_id = $1",
					params=(order_id,),
					delay_after=0.05 * idx,
					description="writer_read",
				),
				StatementPlan(
					sql="UPDATE orders SET quantity = quantity + $2 WHERE order_id = $1",
					params=(order_id, increment),
					description="writer_update",
				),
			]
			plans.append(ClientPlan(f"writer-{idx+1}", node, "writer", statements))
		return plans

	async def _execute_client(self, state: RunState, plan: ClientPlan) -> None:
		state.client_status[plan.client_id] = {"status": "running", "node": plan.node, "role": plan.role}
		dsn = self._node_dsns.get(plan.node)
		if not dsn:
			raise RuntimeError(f"Missing DSN for node {plan.node}")
		conn = await self._connection_factory(dsn)
		try:
			await conn.execute(f"BEGIN TRANSACTION ISOLATION LEVEL {state.payload.isolation_level.sql_clause}")
			for statement in plan.statements:
				if state.cancel_event.is_set():
					raise asyncio.CancelledError
				result = await self._run_statement(conn, statement)
				await state.log(
					"statement",
					client_id=plan.client_id,
					description=statement.description or statement.sql,
					result=result,
				)
				if statement.delay_after:
					await asyncio.sleep(statement.delay_after)
			await conn.execute("COMMIT")
			state.client_status[plan.client_id]["status"] = "committed"
		except asyncio.CancelledError:
			await conn.execute("ROLLBACK")
			state.client_status[plan.client_id]["status"] = "cancelled"
			raise
		except Exception as exc:
			await conn.execute("ROLLBACK")
			sqlstate = getattr(exc, "sqlstate", None)
			if sqlstate == "40001":
				state.serialization_conflicts.append(plan.client_id)
				await state.log("client_serialization_abort", client_id=plan.client_id, error=str(exc))
				state.client_status[plan.client_id]["status"] = "serialization_aborted"
			else:
				await state.log("client_error", client_id=plan.client_id, error=str(exc))
				state.client_status[plan.client_id]["status"] = "error"
				state.status = "failed"
				raise
		finally:
			await conn.close()

	async def _run_statement(self, conn: asyncpg.Connection, statement: StatementPlan) -> Any:
		sql = statement.sql.strip().lower()
		if sql.startswith("select"):
			rows = await conn.fetch(statement.sql, *statement.params)
			return [self._record_to_dict(row) for row in rows]
		return await conn.execute(statement.sql, *statement.params)

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
		return {
			"order_id": str(order_id),
			"initial_quantity": state.initial_quantity,
			"final_quantity": final_quantity,
			"delta": delta,
			"final_states": final_states,
			"isolation_level": state.payload.isolation_level.sql_clause,
			"read_uncommitted_note": state.payload.isolation_level.note,
			"serialization_conflicts": state.serialization_conflicts,
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
