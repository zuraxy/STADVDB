"""Applier worker unit tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

import replication.workers.applier as applier_module
from replication.workers.applier import ApplierWorker


class StubCrud:
	def __init__(self, ops, apply_exception=None):
		self.ops = ops
		self.applied = []
		self.acks = []
		self.marked = []
		self.apply_exception = apply_exception

	async def fetch_unapplied_ops(self, conn, limit=100):
		return [op for op in self.ops if not op.applied]

	async def apply_op_tx(self, conn, op):
		if self.apply_exception:
			raise self.apply_exception
		op.applied = True
		self.applied.append(op.op_id)

	async def insert_ack(self, conn, op_id, node):
		self.acks.append((op_id, node))

	async def mark_op_applied(self, conn, op_id):
		self.marked.append(op_id)
		for op in self.ops:
			if op.op_id == op_id:
				op.applied = True
				break


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
	assert crud.acks == [(within.op_id, settings.node_name)]
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
	assert crud.acks == []
	assert crud.marked == [op.op_id]
	assert worker.skipped_count == 1
