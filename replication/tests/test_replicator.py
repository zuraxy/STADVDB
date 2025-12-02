"""Unit tests for the replicator worker."""

from __future__ import annotations

from dataclasses import replace

import pytest

from replication.config import PeerNode
from replication.workers.replicator import ReplicatorWorker


class StubHTTPClient:
	def __init__(self, payload):
		self.payload = payload
		self.calls = []

	async def get_json(self, url, params=None):
		self.calls.append((url, params))
		return self.payload


class StubCrud:
	def __init__(self, cursor_map=None):
		self.ops = []
		self.cursor_map = cursor_map or {}
		self.cursor_updates = []

	async def insert_op_if_missing(self, conn, op):
		self.ops.append(op)
		return True

	async def load_replication_cursors(self, conn):
		return self.cursor_map

	async def upsert_replication_cursor(self, conn, node, lamport):
		self.cursor_updates.append((node, lamport))


@pytest.mark.asyncio
async def test_replicator_pulls_from_peer(dummy_pool, settings, op_factory) -> None:
	peer = PeerNode(name="node0", base_url="http://node0:8000")
	op = op_factory(10)
	http_client = StubHTTPClient([op.model_dump()])
	stub_crud = StubCrud()
	worker = ReplicatorWorker(
		dummy_pool,
		replace(settings, peer_nodes=[peer]),
		http_client=http_client,
		crud_module=stub_crud,
	)

	await worker._load_cursors()
	await worker.poll_once()

	assert stub_crud.ops[0].lamport == 10
	assert worker.last_seen[peer.base_url] == 10
	assert worker.total_inserted == 1
	assert http_client.calls[0][1] == {"since_lamport": -1}
	assert stub_crud.cursor_updates == [(peer.name, 10)]


@pytest.mark.asyncio
async def test_replicator_restores_last_seen_from_cursor(dummy_pool, settings, op_factory) -> None:
	peer = PeerNode(name="node0", base_url="http://node0:8000")
	stub_crud = StubCrud(cursor_map={peer.name: 25})
	worker = ReplicatorWorker(
		dummy_pool,
		replace(settings, peer_nodes=[peer]),
		crud_module=stub_crud,
	)

	await worker._load_cursors()

	assert worker.last_seen[peer.base_url] == 25
