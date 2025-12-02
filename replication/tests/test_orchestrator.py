"""Transaction orchestrator unit tests."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

import pytest

from replication.config import Settings
from replication.orchestrator import (
	IsolationLevel,
	OrchestrationInput,
	ScenarioType,
	TransactionActorInput,
	TransactionOrchestrator,
)


class SerializationError(RuntimeError):
	"""Mimic a PostgreSQL serialization failure."""

	sqlstate = "40001"


class FakeDatabase:
	"""Shared in-memory store per node used by fake connections."""

	def __init__(self):
		self.rows: Dict[str, Dict[UUID, Dict[str, Any]]] = {node: {} for node in ("node0", "node1", "node2")}
		self.latest: Dict[str, UUID | None] = {node: None for node in self.rows}
		self.fail_update_once = False

	async def connect(self, dsn: str):
		node = dsn
		return FakeConnection(self, node)

	def insert_order(self, node: str, order_id: UUID, quantity: int, payload: Dict[str, Any]) -> None:
		now = datetime.now(timezone.utc)
		self.rows[node][order_id] = {
			"order_id": order_id,
			"quantity": quantity,
			"payload": payload,
			"updated_at": now,
		}
		self.latest[node] = order_id

	def set_quantity(self, node: str, order_id: UUID, quantity: int) -> None:
		if order_id not in self.rows[node]:
			self.insert_order(node, order_id, quantity, {})
		else:
			self.rows[node][order_id]["quantity"] = quantity
			self.rows[node][order_id]["updated_at"] = datetime.now(timezone.utc)

	def fetch_latest(self, node: str) -> Dict[str, Any] | None:
		order_id = self.latest.get(node)
		if not order_id:
			return None
		row = self.rows[node][order_id]
		return {"order_id": order_id, "quantity": row["quantity"]}

	def fetch_by_id(self, node: str, order_id: UUID) -> Dict[str, Any] | None:
		row = self.rows[node].get(order_id)
		if not row:
			return None
		return row


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
		if statement.startswith("select pg_sleep"):
			return "SELECT 1"
		if statement.startswith("insert into orders"):
			order_id, quantity, payload = params
			self.db.insert_order(self.node, order_id, quantity, payload or {})
			return "INSERT 1"
		if statement.startswith("update orders set quantity"):
			if self.db.fail_update_once:
				self.db.fail_update_once = False
				raise SerializationError("forced serialization abort")
			order_id, new_quantity = params
			self.db.set_quantity(self.node, order_id, new_quantity)
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


@pytest.fixture(autouse=True)
def fast_sleep(monkeypatch):
	async def _fast_sleep(_duration):
		return None

	monkeypatch.setattr("replication.orchestrator.asyncio.sleep", _fast_sleep)


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
	orchestrator = TransactionOrchestrator(local, lambda: False, connection_factory=fake_db.connect)
	return orchestrator, fake_db


@pytest.mark.asyncio
async def test_read_read_scenario_reports_snapshots(orchestrator):
	coordinator, _ = orchestrator
	payload = OrchestrationInput(
		scenario=ScenarioType.READ_READ,
		actors=[
			TransactionActorInput(
				name="reader_a",
				node="node0",
				isolation_level=IsolationLevel.READ_COMMITTED,
				delay_seconds=0.1,
			),
			TransactionActorInput(
				name="reader_b",
				node="node0",
				isolation_level=IsolationLevel.REPEATABLE_READ,
			),
		],
	)
	state = await coordinator.start_run(payload)
	await state.main_task

	assert state.status == "completed"
	assert set(state.client_status.keys()) == {"reader_a", "reader_b"}
	for actor in ("reader_a", "reader_b"):
		result = state.summary["actor_results"][actor]["details"]
		assert "initial_quantity" in result
	assert state.summary["delta"] == 0


@pytest.mark.asyncio
async def test_read_write_applies_new_quantity(orchestrator):
	coordinator, _ = orchestrator
	payload = OrchestrationInput(
		scenario=ScenarioType.READ_WRITE,
		actors=[
			TransactionActorInput(
				name="writer",
				node="node0",
				isolation_level=IsolationLevel.SERIALIZABLE,
				new_quantity=42,
			),
			TransactionActorInput(
				name="reader",
				node="node0",
				isolation_level=IsolationLevel.READ_COMMITTED,
			),
		],
	)
	state = await coordinator.start_run(payload)
	await state.main_task

	assert state.status == "completed"
	assert state.summary["final_quantity"] == 42
	assert state.client_status["writer"]["status"] == "committed"


@pytest.mark.asyncio
async def test_write_write_serialization_conflict(orchestrator):
	coordinator, fake_db = orchestrator
	fake_db.fail_update_once = True
	payload = OrchestrationInput(
		scenario=ScenarioType.WRITE_WRITE,
		actors=[
			TransactionActorInput(
				name="writer_a",
				node="node0",
				isolation_level=IsolationLevel.SERIALIZABLE,
				auto_increment=True,
			),
			TransactionActorInput(
				name="writer_b",
				node="node0",
				isolation_level=IsolationLevel.SERIALIZABLE,
				auto_increment=True,
			),
		],
	)
	state = await coordinator.start_run(payload)
	await state.main_task

	assert state.status == "completed"
	statuses = {info["status"] for info in state.client_status.values()}
	assert "serialization_aborted" in statuses
	assert state.summary["serialization_conflicts"], "conflict list propagated"