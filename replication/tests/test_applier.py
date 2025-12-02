"""Applier worker unit tests."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

import replication.workers.applier as applier_module
from replication.tests.conftest import DummyConn, DummyPool
from replication.workers.applier import ApplierWorker


class StubCrud:
	def __init__(self, ops, apply_exception=None, cursor_map=None):
		self.ops = ops
		self.applied = []
		self.acks = []
		self.marked = []
		self.apply_exception = apply_exception
		self.cursor_map = cursor_map or {"node0": 0}
		self.current_worker = None

	async def fetch_unapplied_ops(self, conn, limit=100):
		for op in self.ops:
			if op.applied:
				continue
			locked_by = getattr(op, "locked_by", None)
			if locked_by and locked_by != self.current_worker:
				continue
			if not locked_by:
				op.locked_by = self.current_worker
			return [op]
		return []

	async def apply_op_tx(self, conn, op, use_transaction=True):
		if self.apply_exception:
			raise self.apply_exception
		op.applied = True
		op.locked_by = None
		self.applied.append(op.op_id)

	async def insert_ack(self, conn, op_id, node):
		self.acks.append((op_id, node))

	async def mark_op_applied(self, conn, op_id):
		self.marked.append(op_id)
		for op in self.ops:
			if op.op_id == op_id:
				op.applied = True
				op.locked_by = None
				break

	async def load_replication_cursors(self, conn):
		return self.cursor_map


class TrackingApplier(ApplierWorker):
	async def _next_locked_op(self, conn):
		if hasattr(self.crud, "current_worker"):
			self.crud.current_worker = self.worker_id
		return await super()._next_locked_op(conn)


@pytest.mark.asyncio
async def test_applier_is_idempotent(dummy_pool, settings, op_factory) -> None:
	op = op_factory(1)
	crud = StubCrud([op])
	worker = ApplierWorker(dummy_pool, settings, crud_module=crud)

	await worker.apply_once()
	await worker.apply_once()

	assert crud.applied == [op.op_id]
	assert crud.acks == [(op.op_id, settings.node_name)]


@pytest.mark.asyncio
async def test_applier_skips_ops_outside_partition(dummy_pool, settings, op_factory) -> None:
	within = op_factory(1, quantity=2)
	outside = op_factory(2, quantity=10)
	crud = StubCrud([within, outside])
	worker = ApplierWorker(dummy_pool, settings, crud_module=crud)

	await worker.apply_once()

	assert crud.applied == [within.op_id]
	assert crud.acks == [
		(within.op_id, settings.node_name),
		(outside.op_id, settings.node_name),
	]
	assert crud.marked == [outside.op_id]


@pytest.mark.asyncio
async def test_applier_respects_payload_quantity_on_node2(dummy_pool, settings, op_factory) -> None:
	node2_settings = replace(settings, node_name="node2")
	op = op_factory(5, quantity=6)
	crud = StubCrud([op])
	worker = ApplierWorker(dummy_pool, node2_settings, crud_module=crud)

	await worker.apply_once()

	assert crud.applied == [op.op_id]
	assert crud.acks == [(op.op_id, node2_settings.node_name)]
	assert crud.marked == []


@pytest.mark.asyncio
async def test_applier_uses_local_lookup_when_payload_missing(dummy_pool, settings, op_factory) -> None:
	node2_settings = replace(settings, node_name="node2")
	op = op_factory(6, quantity=1)
	op.payload = {"payload": {"demo": True}}
	dummy_pool.conn.local_rows[op.row_id] = 6
	crud = StubCrud([op])
	worker = ApplierWorker(dummy_pool, node2_settings, crud_module=crud)

	await worker.apply_once()

	assert crud.applied == [op.op_id]
	assert crud.acks == [(op.op_id, node2_settings.node_name)]
	assert crud.marked == []


@pytest.mark.asyncio
async def test_applier_apply_and_catch_marks_skipped(monkeypatch, dummy_pool, settings, op_factory) -> None:
	class FakeCheckViolationError(Exception):
		pass

	monkeypatch.setattr(
		applier_module.apg_exceptions,
		"CheckViolationError",
		FakeCheckViolationError,
		raising=False,
	)
	node2_settings = replace(settings, node_name="node2")
	op = op_factory(7, quantity=3)
	op.payload = {"quantity": 3, "target_node": "node2"}
	crud = StubCrud([op], apply_exception=FakeCheckViolationError("violates qty constraint"))
	worker = ApplierWorker(dummy_pool, node2_settings, crud_module=crud)

	await worker.apply_once()

	assert crud.applied == []
	assert crud.acks == [(op.op_id, node2_settings.node_name)]
	assert crud.marked == [op.op_id]
	assert worker.skipped_count == 1


@pytest.mark.asyncio
async def test_applier_retries_remote_lookup_then_applies(dummy_pool, settings, op_factory) -> None:
	op = op_factory(8, quantity=1)
	op.payload = {"payload": {"demo": True}}
	crud = StubCrud([op])
	worker = ApplierWorker(dummy_pool, settings, crud_module=crud)
	call_count = {"value": 0}

	async def fake_lookup(row_id):
		call_count["value"] += 1
		if call_count["value"] < 3:
			return None, "error"
		return 2, "ok"

	worker._lookup_remote_quantity = fake_lookup  # type: ignore[attr-defined]

	await worker.apply_once()

	assert crud.applied == [op.op_id]
	assert worker.retry_count == 2
	assert call_count["value"] == 3


@pytest.mark.asyncio
async def test_applier_uses_cursor_cache_for_logging(caplog, dummy_pool, settings, op_factory) -> None:
	settings = replace(settings, applier_debug=True)
	op = op_factory(9, quantity=2)
	crud = StubCrud([op], cursor_map={"node0": 42})
	worker = ApplierWorker(dummy_pool, settings, crud_module=crud)

	with caplog.at_level("DEBUG", logger="replication.workers.applier"):
		await worker.apply_once()

	assert any("last_seen=42" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_applier_max_attempts_triggers_apply_and_skip(monkeypatch, dummy_pool, settings, op_factory) -> None:
	class FakeCheckViolationError(Exception):
		pass

	monkeypatch.setattr(
		applier_module.apg_exceptions,
		"CheckViolationError",
		FakeCheckViolationError,
		raising=False,
	)
	limited_settings = replace(settings, applier_max_attempts=1)
	op = op_factory(10, quantity=1)
	op.payload = {"payload": {}}
	crud = StubCrud([op], apply_exception=FakeCheckViolationError("violates"))
	worker = ApplierWorker(dummy_pool, limited_settings, crud_module=crud)

	async def always_fail_lookup(row_id):
		return None, "error"

	worker._lookup_remote_quantity = always_fail_lookup  # type: ignore[attr-defined]

	await worker.apply_once()

	assert crud.applied == []
	assert crud.marked == [op.op_id]
	assert worker.skipped_count == 1


@pytest.mark.asyncio
async def test_concurrent_appliers_do_not_double_apply(dummy_pool, settings, op_factory) -> None:
	shared_conn = DummyConn()
	pool_a = DummyPool(shared_conn)
	pool_b = DummyPool(shared_conn)
	first = op_factory(11, quantity=2)
	second = op_factory(12, quantity=3)
	crud = StubCrud([first, second])
	worker_a = TrackingApplier(pool_a, settings, crud_module=crud, worker_id="worker-a")
	worker_b = TrackingApplier(pool_b, settings, crud_module=crud, worker_id="worker-b")

	await asyncio.gather(worker_a.apply_once(), worker_b.apply_once())

	assert set(crud.applied) == {first.op_id, second.op_id}
	assert crud.marked == []
