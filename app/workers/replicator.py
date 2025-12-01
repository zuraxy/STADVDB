"""Pull-based replication worker."""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional

from .. import crud
from ..config import PeerNode, Settings
from ..models import OpRecord
from ..utils.http_client import HTTPClient

_LOGGER = logging.getLogger(__name__)


class ReplicatorWorker:
    """Periodically pulls ops from peer nodes and stores them locally."""

    def __init__(
        self,
        pool,
        settings: Settings,
        http_client: Optional[HTTPClient] = None,
        crud_module=crud,
    ) -> None:
        self.pool = pool
        self.settings = settings
        self.http_client = http_client or HTTPClient()
        self.crud = crud_module
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self.last_seen: Dict[str, int] = {peer.base_url: -1 for peer in settings.peer_nodes}
        self.total_inserted = 0
        self.last_error: Optional[str] = None

    async def start(self) -> None:
        if self._task is None:
            self._stop_event.clear()
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            await self.poll_once()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.settings.poll_interval)
            except asyncio.TimeoutError:
                continue

    async def poll_once(self) -> None:
        for peer in self.settings.peer_nodes:
            if peer.name == self.settings.node_name:
                continue
            await self._poll_peer(peer)

    async def _poll_peer(self, peer: PeerNode) -> None:
        since = self.last_seen.get(peer.base_url, -1)
        try:
            payload = await self.http_client.get_json(
                f"{peer.base_url}/oplog",
                params={"since_lamport": since},
            )
            ops = [OpRecord(**item) for item in payload]
            if not ops:
                self.last_error = None
                return
            async with self.pool.acquire() as conn:
                for op in ops:
                    inserted = await self.crud.insert_op_if_missing(conn, op)
                    if inserted:
                        self.total_inserted += 1
                max_lamport = max(op.lamport for op in ops)
                self.last_seen[peer.base_url] = max(self.last_seen.get(peer.base_url, -1), max_lamport)
            self.last_error = None
        except Exception as exc:  # pragma: no cover - exercised by integration tests
            _LOGGER.exception("Failed to replicate from %s", peer.base_url)
            self.last_error = str(exc)

    def metrics(self) -> Dict[str, object]:
        return {
            "last_seen": self.last_seen,
            "total_inserted": self.total_inserted,
            "last_error": self.last_error,
        }
