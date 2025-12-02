"""Transaction orchestrator regression tests covering param-driven scenarios."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

import pytest

from replication.config import Settings
from replication.orchestrator import (
	IsolationLevel,
	OrchestrationParameters,
	ScenarioKind,
	TransactionOrchestrator,
)


class SerializationError(RuntimeError):
	"""Mimic a PostgreSQL serialization failure."""

	sqlstate = "40001"


class FakeDatabase:
	"""Minimal per-node datastore to simulate asyncpg interactions."""

	def __init__(self):
		self.rows: Dict[str, Dict[UUID, Dict[str, Any]]] = {node: {} for node in ("node0", "node1", "node2")}
		self.latest: Dict[str, UUID | None] = {node: None for node in self.rows}
		self.fail_update_once = False

	async def connect(self, dsn: str):
		return FakeConnection(self, dsn)

	def insert_order(self, node: str, order_id: UUID, quantity: int, payload: Dict[str, Any]) -> None:
		now = datetime.now(timezone.utc)
		self.rows[node][order_id] = {
			"order_id": order_id,
			"quantity": quantity,
			"payload": payload,
			"updated_at": now,
		}
		self.latest[node] = order_id

	def set_order(self, node: str, order_id: UUID, quantity: int) -> None:
		if order_id not in self.rows[node]:
			self.insert_order(node, order_id, quantity, {})
		else:
			self.rows[node][order_id]["quantity"] = quantity
			self.rows[node][order_id]["updated_at"] = datetime.now(timezone.utc)

	def increment_order(self, node: str, order_id: UUID, increment: int) -> None:
		if order_id not in self.rows[node]:
			self.insert_order(node, order_id, increment, {})
		else:
			self.rows[node][order_id]["quantity"] += increment
			self.rows[node][order_id]["updated_at"] = datetime.now(timezone.utc)

	def fetch_latest(self, node: str) -> Dict[str, Any] | None:
		order_id = self.latest.get(node)
		return self.rows[node].get(order_id) if order_id else None

	def fetch_by_id(self, node: str, order_id: UUID) -> Dict[str, Any] | None:
		return self.rows[node].get(order_id)


class FakeConnection:
	def __init__(self, db: FakeDatabase, node: str):
		self.db = db
		self.node = node

	async def execute(self, sql: str, *params):
		statement = " ".join(sql.strip().split()).lower()
		if statement.startswith("begin"):
			return "BEGIN"
		if statement.startswith("commit"):
			return "COMMIT"
		if statement.startswith("rollback"):
			return "ROLLBACK"
		if "pg_sleep" in statement:
			return "SELECT 1"
		if statement.startswith("insert into orders"):
			order_id, quantity, payload = params
			self.db.insert_order(self.node, order_id, quantity, payload or {})
			return "INSERT 1"
		if "set quantity = $1" in statement:
			order_id = params[1]
			value = params[0]
			self.db.set_order(self.node, order_id, value)
			return "UPDATE 1"
		if "set quantity = quantity +" in statement:
			if self.db.fail_update_once:
				self.db.fail_update_once = False
				raise SerializationError("forced serialization abort")
			order_id = params[0]
			increment = params[1]
			self.db.increment_order(self.node, order_id, increment)
			return "UPDATE 1"
		return "EXEC"

	async def fetchrow(self, sql: str, *params):
		statement = " ".join(sql.strip().split()).lower()
		if "order by updated_at desc" in statement:
			return self.db.fetch_latest(self.node)
		if "from orders where order_id" in statement:
			return self.db.fetch_by_id(self.node, params[0])
		return None

	async def fetch(self, sql: str, *params):
		row = await self.fetchrow(sql, *params)
		return [row] if row else []

	async def close(self):
		return None


@pytest.fixture
def orchestrator(settings: Settings):
	local = replace(
		settings,
		node_name="node0",
		default_master="node0",
		database_dsn="node0",
		node0_dsn="node0",
		node1_dsn="node1",
		node2_dsn="node2",
	)
	fake_db = FakeDatabase()
	coordinator = TransactionOrchestrator(local, lambda: False, connection_factory=fake_db.connect)
	return coordinator, fake_db


@pytest.mark.asyncio
async def test_read_read_clients_capture_snapshots(orchestrator):
	coordinator, _ = orchestrator
	parameters = OrchestrationParameters(
		scenario=ScenarioKind.READ_READ,
		isolation_level=IsolationLevel.REPEATABLE_READ,
		parallel_clients=2,
		node_x="node0",
		node_y="node1",
	)
	state = await coordinator.start_run(parameters)
	await state.main_task

	assert state.status == "completed"
	for info in state.client_status.values():
		actions = [step["action"] for step in info["steps"]]
		assert actions[0] == "BEGIN"
		assert actions.count("SELECT") >= 2
		assert actions[-1] == "COMMIT"


@pytest.mark.asyncio
async def test_read_write_writer_overrides_quantity(orchestrator):
	coordinator, _ = orchestrator
	parameters = OrchestrationParameters(
		scenario=ScenarioKind.READ_WRITE,
		isolation_level=IsolationLevel.READ_COMMITTED,
		parallel_clients=2,
		new_value_1=42,
	)
	state = await coordinator.start_run(parameters)
	await state.main_task

	assert state.status == "completed"
	assert state.summary["final_quantity"] == 42
	assert state.client_status["writer-1"]["status"] == "committed"


@pytest.mark.asyncio
async def test_write_write_serialization_abort_recorded(orchestrator):
	coordinator, fake_db = orchestrator
	fake_db.fail_update_once = True
	parameters = OrchestrationParameters(
		scenario=ScenarioKind.WRITE_WRITE,
		isolation_level=IsolationLevel.SERIALIZABLE,
		parallel_clients=2,
		new_value_1=1,
		new_value_2=1,
	)
	state = await coordinator.start_run(parameters)
	await state.main_task

	assert state.status in {"completed", "failed"}
	assert state.summary["serialization_conflicts"], "conflict captured"
	assert any(info["status"] == "serialization_aborted" for info in state.client_status.values())