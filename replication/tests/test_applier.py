"""Applier worker unit tests."""

from __future__ import annotations

import pytest

from replication.workers.applier import ApplierWorker


class StubCrud:
	def __init__(self, ops):
		self.ops = ops
		self.applied = []
		self.acks = []
		self.marked = []

	async def fetch_unapplied_ops(self, conn, limit=100):
		return [op for op in self.ops if not op.applied]

	async def apply_op_tx(self, conn, op):
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
