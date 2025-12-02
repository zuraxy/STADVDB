"""Op-log applier worker."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .. import crud
from ..config import Settings
from ..utils.partition import can_accept_partition

_LOGGER = logging.getLogger(__name__)


class ApplierWorker:
    """Continuously applies unapplied operations."""

    def __init__(self, pool, settings: Settings, crud_module=crud) -> None:
        self.pool = pool
        self.settings = settings
        self.crud = crud_module
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self.applied_count = 0
        self.skipped_count = 0
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
            await self.apply_once()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.settings.applier_interval)
            except asyncio.TimeoutError:
                continue

    async def apply_once(self) -> None:
        async with self.pool.acquire() as conn:
            ops = await self.crud.fetch_unapplied_ops(conn)
            if not ops:
                self.last_error = None
                return
            for op in ops:
                if not self._should_apply(op):
                    await self.crud.mark_op_applied(conn, op.op_id)
                    self.skipped_count += 1
                    continue
                try:
                    await self.crud.apply_op_tx(conn, op)
                    await self.crud.insert_ack(conn, op.op_id, self.settings.node_name)
                    self.applied_count += 1
                except Exception as exc:  # pragma: no cover - exercised via integration tests
                    _LOGGER.exception("Failed to apply op %s", op.op_id)
                    self.last_error = str(exc)
                    return

    def _should_apply(self, op) -> bool:
        if self.settings.node_name == self.settings.default_master:
            return True
        payload = op.payload or {}
        quantity = payload.get("quantity")
        if quantity is None:
            return True
        return can_accept_partition(self.settings.node_name, quantity, self.settings.partition_rule)

    def metrics(self) -> dict:
        return {
            "applied_count": self.applied_count,
            "skipped_count": self.skipped_count,
            "last_error": self.last_error,
        }
