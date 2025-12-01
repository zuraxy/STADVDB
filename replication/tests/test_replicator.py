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
	def __init__(self):
		self.ops = []

	async def insert_op_if_missing(self, conn, op):
		self.ops.append(op)
		return True


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

	await worker.poll_once()

	assert stub_crud.ops[0].lamport == 10
	assert worker.last_seen[peer.base_url] == 10
	assert worker.total_inserted == 1
	assert http_client.calls[0][1] == {"since_lamport": -1}
