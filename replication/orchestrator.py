"""Transaction orchestrator for concurrent transaction scenarios."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import UUID, uuid4

import asyncpg

from .config import Settings

try:  # pragma: no cover - fallback for nodes that lack the helper file
	from .utils.iso_map import iso_clause_for, iso_note_for
except ModuleNotFoundError:  # pragma: no cover - defensive path for older deployments
	LOGGER = logging.getLogger(__name__)
	LOGGER.warning("replication.utils.iso_map missing; falling back to inline mapping")

	def iso_clause_for(level: str) -> str:
		mapping = {
			"READ_UNCOMMITTED": "READ COMMITTED",
			"READ_COMMITTED": "READ COMMITTED",
			"REPEATABLE_READ": "REPEATABLE READ",
			"SERIALIZABLE": "SERIALIZABLE",
		}
		return mapping.get(level, "READ COMMITTED")

	def iso_note_for(level: str) -> Optional[str]:
		if level == "READ_UNCOMMITTED":
			return "PostgreSQL promotes READ UNCOMMITTED to READ COMMITTED."
		return None

LOGGER = logging.getLogger(__name__)
DEFAULT_START_QUANTITY = 10


class IsolationLevel(str, Enum):
	"""Supported isolation levels for orchestration runs."""

	READ_UNCOMMITTED = "READ_UNCOMMITTED"
	READ_COMMITTED = "READ_COMMITTED"
	REPEATABLE_READ = "REPEATABLE_READ"
	SERIALIZABLE = "SERIALIZABLE"

	@property
	def sql_clause(self) -> str:
		return iso_clause_for(self.value)

	@property
	def note(self) -> Optional[str]:
		return iso_note_for(self.value)


class ScenarioKind(str, Enum):
	"""Built-in concurrency scenarios supported by the orchestrator."""

	READ_READ = "read_read"
	READ_WRITE = "read_write"
	WRITE_WRITE = "write_write"
	NON_REPEATABLE_READ = "non_repeatable_read"
	PHANTOM_READ = "phantom_read"


@dataclass
class OrchestrationParameters:
	"""Normalized parameters provided by the API/UI layer."""

	scenario: ScenarioKind
	isolation_level: IsolationLevel
	parallel_clients: int
	order_id: Optional[UUID] = None
	node_x: str = "node0"
	node_y: str = "node1"
	new_value_1: Optional[int] = None
	new_value_2: Optional[int] = None


@dataclass
class TransactionInstruction:
	"""Single SQL statement executed inside a transaction."""

	action: str
	sql: str
	params: Tuple[Any, ...] = field(default_factory=tuple)
	capture_results: bool = True


@dataclass
class ClientScript:
	"""Declarative script executed by one orchestrator client."""

	client_id: str
	role: str
	node: str
	instructions: List[TransactionInstruction]


class RunState:
	"""Mutable in-memory state for a single orchestrator run."""

	def __init__(self, run_id: str, parameters: OrchestrationParameters):
		self.id = run_id
		self.parameters = parameters
		self.status: str = "running"
		self.created_at = datetime.now(timezone.utc)
		self.finished_at: Optional[datetime] = None
		self.logs: List[Dict[str, Any]] = []
		self.summary: Optional[Dict[str, Any]] = None
		self.client_status: Dict[str, Dict[str, Any]] = {}
		self.order_id: Optional[UUID] = None
		self.initial_quantity: Optional[int] = None
		self.serialization_conflicts: List[str] = []
		self.cancel_event = asyncio.Event()
		self.main_task: Optional[asyncio.Task] = None
		self._log_lock = asyncio.Lock()
		self._listeners: List[asyncio.Queue] = []
		# Timing metrics
		self.client_timings: Dict[str, Dict[str, float]] = {}
		self.start_time: Optional[float] = None
		self.end_time: Optional[float] = None

	async def log(self, event: str, **details: Any) -> None:
		"""Persist + broadcast a structured log entry."""

		entry = {
			"timestamp": datetime.now(timezone.utc).isoformat(),
			"event": event,
			"details": details,
		}
		async with self._log_lock:
			self.logs.append(entry)
		await self._broadcast(entry)

	def register_client(self, script: ClientScript) -> None:
		self.client_status[script.client_id] = {
			"client_id": script.client_id,
			"role": script.role,
			"node": script.node,
			"status": "pending",
			"start_time": None,
			"end_time": None,
			"steps": [],
			"error": None,
		}

	async def append_step(
		self,
		client_id: str,
		action: str,
		sql: Optional[str] = None,
		result: Any = None,
		error: Optional[str] = None,
		duration_ms: Optional[float] = None,
	) -> None:
		entry = {
			"timestamp": datetime.now(timezone.utc).isoformat(),
			"action": action,
			"sql": sql,
			"result": result,
			"error": error,
			"duration_ms": duration_ms,
		}
		self.client_status[client_id]["steps"].append(entry)
		await self.log("client_step", client_id=client_id, action=action, error=error)

	def snapshot(self) -> Dict[str, Any]:
		return {
			"run_id": self.id,
			"scenario": self.parameters.scenario.value,
			"status": self.status,
			"created_at": self.created_at.isoformat(),
			"finished_at": self.finished_at.isoformat() if self.finished_at else None,
			"clients": self.client_status,
			"result_summary": self.summary,
		}

	def mark_finished(self, status: str) -> None:
		self.status = status
		self.finished_at = datetime.now(timezone.utc)

	def register_listener(self) -> asyncio.Queue:
		queue: asyncio.Queue = asyncio.Queue()
		self._listeners.append(queue)
		return queue

	def unregister_listener(self, queue: asyncio.Queue) -> None:
		if queue in self._listeners:
			self._listeners.remove(queue)

	async def _broadcast(self, entry: Dict[str, Any]) -> None:
		for queue in list(self._listeners):
			try:
				queue.put_nowait(entry)
			except asyncio.QueueFull:  # pragma: no cover - defensive
				LOGGER.warning("Dropping orchestrator event; slow consumer")


class TransactionOrchestrator:
	"""Coordinates concurrent SQL scripts across replica nodes."""

	sleep_seconds: float = 2.0

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
		mapping[self.settings.node_name.lower()] = self.settings.database_dsn
		return mapping

	def _primary_node(self) -> str:
		if self.settings.node_name == self.settings.default_master:
			return self.settings.default_master
		if self._promoted_flag():
			return self.settings.node_name
		return self.settings.default_master

	async def start_run(self, parameters: OrchestrationParameters) -> RunState:
		run_id = str(uuid4())
		state = RunState(run_id, parameters)
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

	async def stream_logs(self, run_id: str) -> Optional[AsyncIterator[str]]:
		state = self._runs.get(run_id)
		if not state:
			return None

		async def event_stream() -> AsyncIterator[str]:
			for entry in state.logs:
				yield self._format_sse(entry)
			queue = state.register_listener()
			try:
				while True:
					entry = await queue.get()
					yield self._format_sse(entry)
					if entry.get("event") == "run_finished":
						break
			finally:
				state.unregister_listener(queue)

		return event_stream()

	async def wait_for_run(self, run_id: str, timeout: float = 30.0) -> None:
		state = self._runs.get(run_id)
		if not state or not state.main_task:
			return
		await asyncio.wait_for(state.main_task, timeout)

	async def _execute_run(self, state: RunState) -> None:
		try:
			order_id, quantity = await self._ensure_target_order(state.parameters)
			state.order_id = order_id
			state.initial_quantity = quantity
			scripts = self._build_scripts(state.parameters, order_id)
			for script in scripts:
				state.register_client(script)
			await state.log("scenario_compiled", order_id=str(order_id), clients=len(scripts))
			tasks = [asyncio.create_task(self._execute_client(state, script)) for script in scripts]
			results = await asyncio.gather(*tasks, return_exceptions=True)
			if any(isinstance(result, Exception) for result in results) and state.status == "running":
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
			await state.log("run_finished", status=state.status)

	async def _ensure_target_order(self, parameters: OrchestrationParameters) -> Tuple[UUID, int]:
		if parameters.order_id:
			found = await self._locate_order(parameters.order_id)
			if found:
				return found
			await self._create_order(parameters.order_id, DEFAULT_START_QUANTITY)
			return parameters.order_id, DEFAULT_START_QUANTITY
		primary = self._primary_node().lower()
		dsn = self._node_dsns.get(primary)
		import asyncpg

		from .config import Settings

		LOGGER = logging.getLogger(__name__)

		try:  # pragma: no cover - fallback for nodes that lack the helper file
			from .utils.iso_map import iso_clause_for, iso_note_for
		except ModuleNotFoundError:  # pragma: no cover - defensive path for older deployments
			LOGGER.warning("replication.utils.iso_map missing; using inline isolation map")

			def iso_clause_for(level: str) -> str:
				mapping = {
					"READ_UNCOMMITTED": "READ COMMITTED",
					"READ_COMMITTED": "READ COMMITTED",
					"REPEATABLE_READ": "REPEATABLE READ",
					"SERIALIZABLE": "SERIALIZABLE",
				}
				return mapping.get(level, "READ COMMITTED")

			def iso_note_for(level: str) -> Optional[str]:
				if level == "READ_UNCOMMITTED":
					return "PostgreSQL promotes READ UNCOMMITTED to READ COMMITTED."
				return None
				if row:
					return row["order_id"], row["quantity"]
			finally:
				await conn.close()
		return None

	async def _create_order(self, order_id: UUID, quantity: int) -> None:
		primary = self._primary_node().lower()
		dsn = self._node_dsns.get(primary)
		if not dsn:
			raise RuntimeError(f"Missing DSN for node {primary}")
		conn = await self._connection_factory(dsn)
		try:
			await conn.execute(
				"""
				INSERT INTO orders (order_id, quantity, payload, created_at, updated_at)
				VALUES ($1, $2, $3::jsonb, NOW(), NOW())
				ON CONFLICT (order_id) DO NOTHING
				""",
				order_id,
				quantity,
				json.dumps({}),
			)
		finally:
			await conn.close()

	def _build_scripts(self, parameters: OrchestrationParameters, order_id: UUID) -> List[ClientScript]:
		if parameters.scenario is ScenarioKind.READ_READ:
			return self._build_read_read(parameters, order_id)
		if parameters.scenario is ScenarioKind.READ_WRITE:
			return self._build_read_write(parameters, order_id)
		if parameters.scenario is ScenarioKind.WRITE_WRITE:
			return self._build_write_write(parameters, order_id)
		if parameters.scenario is ScenarioKind.NON_REPEATABLE_READ:
			return self._build_non_repeatable_read(parameters, order_id)
		if parameters.scenario is ScenarioKind.PHANTOM_READ:
			return self._build_phantom_read(parameters, order_id)
		raise ValueError(f"Unsupported scenario {parameters.scenario}")

	def _build_read_read(self, parameters: OrchestrationParameters, order_id: UUID) -> List[ClientScript]:
		nodes = self._resolved_nodes([parameters.node_x, parameters.node_y])
		clients: List[ClientScript] = []
		for idx in range(max(2, parameters.parallel_clients)):
			node = nodes[idx % len(nodes)]
			instructions = [
				TransactionInstruction(
					action="SELECT",
					sql="SELECT quantity FROM orders WHERE order_id = $1",
					params=(order_id,),
					capture_results=True,
				),
				TransactionInstruction(
					action="SLEEP",
					sql="SELECT pg_sleep($1)",
					params=(self.sleep_seconds,),
					capture_results=False,
				),
				TransactionInstruction(
					action="SELECT",
					sql="SELECT quantity FROM orders WHERE order_id = $1",
					params=(order_id,),
					capture_results=True,
				),
			]
			clients.append(
				ClientScript(
					client_id=f"reader-{idx+1}",
					role="reader",
					node=node,
					instructions=instructions,
				)
			)
		return clients

	def _build_read_write(self, parameters: OrchestrationParameters, order_id: UUID) -> List[ClientScript]:
		writer_node = self._resolved_nodes([parameters.node_x])[0]
		reader_nodes = self._resolved_nodes([parameters.node_y])
		writer_value = parameters.new_value_1 if parameters.new_value_1 is not None else DEFAULT_START_QUANTITY + 1
		writer_script = ClientScript(
			client_id="writer-1",
			role="writer",
			node=writer_node,
			instructions=[
				TransactionInstruction(
					action="SELECT",
					sql="SELECT quantity FROM orders WHERE order_id = $1",
					params=(order_id,),
					capture_results=True,
				),
				TransactionInstruction(
					action="UPDATE",
					sql="UPDATE orders SET quantity = $1, updated_at = NOW() WHERE order_id = $2",
					params=(writer_value, order_id),
					capture_results=False,
				),
				TransactionInstruction(
					action="SLEEP",
					sql="SELECT pg_sleep($1)",
					params=(self.sleep_seconds,),
					capture_results=False,
				),
			]
		)
		clients: List[ClientScript] = [writer_script]
		reader_count = max(1, parameters.parallel_clients - 1)
		for idx in range(reader_count):
			node = reader_nodes[idx % len(reader_nodes)]
			clients.append(
				ClientScript(
					client_id=f"reader-{idx+1}",
					role="reader",
					node=node,
					instructions=[
						TransactionInstruction(
							action="SELECT",
							sql="SELECT quantity FROM orders WHERE order_id = $1",
							params=(order_id,),
							capture_results=True,
						),
					],
				),
			)
		return clients

	def _build_write_write(self, parameters: OrchestrationParameters, order_id: UUID) -> List[ClientScript]:
		node_a = self._resolved_nodes([parameters.node_x])[0]
		node_b = self._resolved_nodes([parameters.node_y])[0]
		inc_a = parameters.new_value_1 if parameters.new_value_1 is not None else 1
		inc_b = parameters.new_value_2 if parameters.new_value_2 is not None else 1
		clients = [
			ClientScript(
				client_id="writer-a",
				role="writer",
				node=node_a,
				instructions=[
					TransactionInstruction(
						action="UPDATE",
						sql="UPDATE orders SET quantity = quantity + $2, updated_at = NOW() WHERE order_id = $1",
						params=(order_id, inc_a),
						capture_results=False,
					),
					TransactionInstruction(
						action="SLEEP",
						sql="SELECT pg_sleep($1)",
						params=(self.sleep_seconds,),
						capture_results=False,
					),
					TransactionInstruction(
						action="SELECT",
						sql="SELECT quantity FROM orders WHERE order_id = $1",
						params=(order_id,),
						capture_results=True,
					),
				],
			),
			ClientScript(
				client_id="writer-b",
				role="writer",
				node=node_b,
				instructions=[
					TransactionInstruction(
						action="UPDATE",
						sql="UPDATE orders SET quantity = quantity + $2, updated_at = NOW() WHERE order_id = $1",
						params=(order_id, inc_b),
						capture_results=False,
					),
					TransactionInstruction(
						action="SELECT",
						sql="SELECT quantity FROM orders WHERE order_id = $1",
						params=(order_id,),
						capture_results=True,
					),
				],
			),
		]
		return clients

	def _build_non_repeatable_read(self, parameters: OrchestrationParameters, order_id: UUID) -> List[ClientScript]:
		"""Test non-repeatable read: Reader reads, writer updates, reader reads again."""
		reader_node = self._resolved_nodes([parameters.node_x])[0]
		writer_node = self._resolved_nodes([parameters.node_y])[0]
		writer_value = parameters.new_value_1 if parameters.new_value_1 is not None else DEFAULT_START_QUANTITY + 5
		
		# Reader: long-running transaction with two reads separated by sleep
		reader_script = ClientScript(
			client_id="reader-1",
			role="reader",
			node=reader_node,
			instructions=[
				TransactionInstruction(
					action="SELECT_1",
					sql="SELECT quantity FROM orders WHERE order_id = $1",
					params=(order_id,),
					capture_results=True,
				),
				TransactionInstruction(
					action="SLEEP",
					sql="SELECT pg_sleep($1)",
					params=(self.sleep_seconds,),
					capture_results=False,
				),
				TransactionInstruction(
					action="SELECT_2",
					sql="SELECT quantity FROM orders WHERE order_id = $1",
					params=(order_id,),
					capture_results=True,
				),
			],
		)
		
		# Writer: updates the value during reader's sleep
		writer_script = ClientScript(
			client_id="writer-1",
			role="writer",
			node=writer_node,
			instructions=[
				TransactionInstruction(
					action="SLEEP",
					sql="SELECT pg_sleep($1)",
					params=(self.sleep_seconds / 2,),  # Start halfway through reader's first sleep
					capture_results=False,
				),
				TransactionInstruction(
					action="UPDATE",
					sql="UPDATE orders SET quantity = $1, updated_at = NOW() WHERE order_id = $2",
					params=(writer_value, order_id),
					capture_results=False,
				),
			],
		)
		
		return [reader_script, writer_script]

	def _build_phantom_read(self, parameters: OrchestrationParameters, order_id: UUID) -> List[ClientScript]:
		"""Test phantom read: Reader counts rows, writer inserts, reader counts again."""
		reader_node = self._resolved_nodes([parameters.node_x])[0]
		writer_node = self._resolved_nodes([parameters.node_y])[0]
		new_quantity = parameters.new_value_1 if parameters.new_value_1 is not None else 3
		
		# Reader: performs range query twice to detect phantoms
		reader_script = ClientScript(
			client_id="reader-1",
			role="reader",
			node=reader_node,
			instructions=[
				# First range query: count orders in quantity range
				TransactionInstruction(
					action="COUNT_1",
					sql="SELECT COUNT(*) as count FROM orders WHERE quantity BETWEEN 1 AND 5",
					params=(),
					capture_results=True,
				),
				# List all matching orders
				TransactionInstruction(
					action="SELECT_RANGE_1",
					sql="SELECT order_id, quantity FROM orders WHERE quantity BETWEEN 1 AND 5 ORDER BY quantity",
					params=(),
					capture_results=True,
				),
				TransactionInstruction(
					action="SLEEP",
					sql="SELECT pg_sleep($1)",
					params=(self.sleep_seconds,),
					capture_results=False,
				),
				# Second range query: same count after writer potentially inserted
				TransactionInstruction(
					action="COUNT_2",
					sql="SELECT COUNT(*) as count FROM orders WHERE quantity BETWEEN 1 AND 5",
					params=(),
					capture_results=True,
				),
				TransactionInstruction(
					action="SELECT_RANGE_2",
					sql="SELECT order_id, quantity FROM orders WHERE quantity BETWEEN 1 AND 5 ORDER BY quantity",
					params=(),
					capture_results=True,
				),
			],
		)
		
		# Writer: inserts new row in the range during reader's transaction
		writer_script = ClientScript(
			client_id="writer-1",
			role="writer",
			node=writer_node,
			instructions=[
				TransactionInstruction(
					action="SLEEP",
					sql="SELECT pg_sleep($1)",
					params=(self.sleep_seconds / 2,),  # Insert halfway through reader's sleep
					capture_results=False,
				),
				TransactionInstruction(
					action="INSERT",
					sql="INSERT INTO orders (order_id, quantity, payload, created_at, updated_at) VALUES (gen_random_uuid(), $1, '{}'::jsonb, NOW(), NOW())",
					params=(new_quantity,),
					capture_results=False,
				),
			],
		)
		
		return [reader_script, writer_script]


	def _resolved_nodes(self, requested: Sequence[str]) -> List[str]:
		nodes: List[str] = []
		for label in requested:
			if not label:
				continue
			normalized = label.lower()
			if normalized in self._node_dsns and self._node_dsns[normalized]:
				nodes.append(normalized)
		if not nodes:
			nodes.append(self._primary_node().lower())
		return nodes

	async def _execute_client(self, state: RunState, script: ClientScript) -> None:
		import time
		
		state.client_status[script.client_id]["status"] = "running"
		client_start = time.perf_counter()
		state.client_status[script.client_id]["start_time"] = client_start
		
		dsn = self._node_dsns.get(script.node)
		if not dsn:
			raise RuntimeError(f"Missing DSN for node {script.node}")
		conn = await self._connection_factory(dsn)
		begin_sql = f"BEGIN TRANSACTION ISOLATION LEVEL {state.parameters.isolation_level.sql_clause}"
		try:
			step_start = time.perf_counter()
			await conn.execute(begin_sql)
			step_duration = (time.perf_counter() - step_start) * 1000
			await state.append_step(script.client_id, "BEGIN", begin_sql, duration_ms=step_duration)
			
			for instruction in script.instructions:
				if state.cancel_event.is_set():
					raise asyncio.CancelledError
				step_start = time.perf_counter()
				result = await self._run_instruction(conn, instruction)
				step_duration = (time.perf_counter() - step_start) * 1000
				await state.append_step(script.client_id, instruction.action, instruction.sql, result, duration_ms=step_duration)
			
			step_start = time.perf_counter()
			await conn.execute("COMMIT")
			step_duration = (time.perf_counter() - step_start) * 1000
			await state.append_step(script.client_id, "COMMIT", "COMMIT", duration_ms=step_duration)
			state.client_status[script.client_id]["status"] = "committed"
		except asyncio.CancelledError:
			await conn.execute("ROLLBACK")
			await state.append_step(script.client_id, "ROLLBACK", "ROLLBACK")
			state.client_status[script.client_id]["status"] = "cancelled"
			raise
		except Exception as exc:
			await conn.execute("ROLLBACK")
			await state.append_step(script.client_id, "ROLLBACK", "ROLLBACK", error=str(exc))
			sqlstate = getattr(exc, "sqlstate", None)
			if sqlstate == "40001":
				state.serialization_conflicts.append(script.client_id)
				state.client_status[script.client_id]["status"] = "serialization_aborted"
				state.client_status[script.client_id]["error"] = str(exc)
				await state.log("client_serialization_abort", client_id=script.client_id, error=str(exc))
			else:
				state.client_status[script.client_id]["status"] = "error"
				state.client_status[script.client_id]["error"] = str(exc)
				state.status = "failed"
				await state.log("client_error", client_id=script.client_id, error=str(exc))
				raise
		finally:
			client_end = time.perf_counter()
			state.client_status[script.client_id]["end_time"] = client_end
			total_duration = (client_end - client_start) * 1000
			state.client_timings[script.client_id] = {
				"total_duration_ms": total_duration,
				"start_time": client_start,
				"end_time": client_end,
			}
			await conn.close()

	async def _run_instruction(self, conn: asyncpg.Connection, instruction: TransactionInstruction) -> Any:
		if instruction.capture_results:
			rows = await conn.fetch(instruction.sql, *instruction.params)
			return [self._record_to_dict(row) for row in rows]
		return await conn.execute(instruction.sql, *instruction.params)

	async def _collect_summary(self, state: RunState) -> Dict[str, Any]:
		if not state.order_id:
			return {}
		final_states: Dict[str, Any] = {}
		for node, dsn in self._node_dsns.items():
			if not dsn:
				final_states[node] = {"available": False}
				continue
			final_states[node] = await self._fetch_node_snapshot(dsn, state.order_id)
		primary_state = final_states.get(self._primary_node().lower(), {})
		final_quantity = primary_state.get("quantity") if isinstance(primary_state, dict) else None
		delta = None
		if final_quantity is not None and state.initial_quantity is not None:
			delta = final_quantity - state.initial_quantity
		verdict = self._derive_verdict(state, final_quantity)
		timing_metrics = self._calculate_timing_metrics(state)
		
		return {
			"order_id": str(state.order_id),
			"initial_quantity": state.initial_quantity,
			"final_quantity": final_quantity,
			"delta": delta,
			"final_states": final_states,
			"isolation_level": state.parameters.isolation_level.sql_clause,
			"read_uncommitted_note": state.parameters.isolation_level.note,
			"serialization_conflicts": state.serialization_conflicts,
			"verdict": verdict,
			"replication_note": "Node snapshots reflect current values per node at query time.",
			"timing_metrics": timing_metrics,
		}

	def _derive_verdict(self, state: RunState, final_quantity: Optional[int]) -> str:
		scenario = state.parameters.scenario.value.replace("_", " ").title()
		iso = state.parameters.isolation_level.value.replace("_", " ")
		statuses = ", ".join(f"{cid}:{info['status']}" for cid, info in state.client_status.items())
		quantity_note = f" final={final_quantity}" if final_quantity is not None else ""
		return f"{scenario} under {iso} → {statuses}.{quantity_note}"

	def _calculate_timing_metrics(self, state: RunState) -> Dict[str, Any]:
		"""Calculate comprehensive timing metrics for the orchestration run."""
		client_metrics = {}
		all_durations = []
		sleep_durations = []
		execution_durations = []
		
		for client_id, timing in state.client_timings.items():
			total_duration = timing["total_duration_ms"]
			all_durations.append(total_duration)
			
			# Calculate step-by-step breakdown
			steps = state.client_status.get(client_id, {}).get("steps", [])
			step_breakdown = {}
			total_sleep_time = 0
			total_execution_time = 0
			
			for step in steps:
				action = step.get("action", "unknown")
				duration = step.get("duration_ms", 0)
				
				if action not in step_breakdown:
					step_breakdown[action] = {"count": 0, "total_ms": 0, "avg_ms": 0}
				
				step_breakdown[action]["count"] += 1
				step_breakdown[action]["total_ms"] += duration
				
				if action == "SLEEP":
					total_sleep_time += duration
					sleep_durations.append(duration)
				else:
					total_execution_time += duration
					execution_durations.append(duration)
			
			# Calculate averages
			for action_data in step_breakdown.values():
				if action_data["count"] > 0:
					action_data["avg_ms"] = round(action_data["total_ms"] / action_data["count"], 2)
			
			client_metrics[client_id] = {
				"total_duration_ms": round(total_duration, 2),
				"sleep_time_ms": round(total_sleep_time, 2),
				"execution_time_ms": round(total_execution_time, 2),
				"step_breakdown": step_breakdown,
			}
		
		# Aggregate metrics
		avg_total = round(sum(all_durations) / len(all_durations), 2) if all_durations else 0
		min_total = round(min(all_durations), 2) if all_durations else 0
		max_total = round(max(all_durations), 2) if all_durations else 0
		
		avg_sleep = round(sum(sleep_durations) / len(sleep_durations), 2) if sleep_durations else 0
		avg_execution = round(sum(execution_durations) / len(execution_durations), 2) if execution_durations else 0
		
		return {
			"client_metrics": client_metrics,
			"aggregate": {
				"avg_total_duration_ms": avg_total,
				"min_total_duration_ms": min_total,
				"max_total_duration_ms": max_total,
				"avg_sleep_time_ms": avg_sleep,
				"avg_execution_time_ms": avg_execution,
				"total_clients": len(client_metrics),
			},
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
	def _format_sse(entry: Dict[str, Any]) -> str:
		return f"data: {json.dumps(entry)}\n\n"

	@staticmethod
	def _record_to_dict(record: Any) -> Dict[str, Any]:
		if hasattr(record, "items"):
			return dict(record.items())
		if isinstance(record, dict):
			return record
		return {"value": str(record)}
