"""Pytest fixtures for worker unit tests."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

import pytest

from replication.config import Settings
from replication.models import OpRecord


class DummyConn:
	"""Simple stand-in for an asyncpg connection."""

	def __init__(self):
		self.local_rows = {}

	async def execute(self, *_, **__):
		return "EXECUTE"

	async def fetch(self, *_, **__):  # pragma: no cover - not used in unit tests
		return []

	async def fetchval(self, *_, **__):  # pragma: no cover - not used in unit tests
		return 0

	async def fetchrow(self, query, *args, **__):
		needle = query.lower()
		if "from orders" in needle and "where order_id" in needle and args:
			quantity = self.local_rows.get(args[0])
			if quantity is None:
				return None
			return {"quantity": quantity}
		return None

	@asynccontextmanager
	async def transaction(self):
		yield


class DummyPool:
	def __init__(self, conn=None):
		self._conn = conn or DummyConn()

	@asynccontextmanager
	async def acquire(self):
		yield self._conn

	@property
	def conn(self) -> DummyConn:
		return self._conn


@pytest.fixture
def dummy_pool() -> DummyPool:
	return DummyPool()


@pytest.fixture
def settings() -> Settings:
	return Settings(
		database_dsn="postgres://test",
		node_name="node1",
		peer_nodes=[],
		poll_interval=1,
		default_master="node0",
		default_master_url="http://node0:8000",
		promoted=False,
		partition_rule=5,
		applier_interval=0.1,
		node0_dsn="node0",
		node1_dsn="node1",
		node2_dsn="node2",
	)


@pytest.fixture
def op_factory() -> Callable[[int, int], OpRecord]:
	def _factory(lamport: int, quantity: int = 1) -> OpRecord:
		now = datetime.now(timezone.utc)
		return OpRecord(
			op_id=uuid4(),
			origin_node="node0",
			op_type="upsert",
			table_name="orders",
			row_id=uuid4(),
			payload={"quantity": quantity, "payload": {"demo": True}},
			ts=now,
			lamport=lamport,
			applied=False,
			applied_ts=None,
		)

	return _factory
