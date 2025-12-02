"""Op-log applier worker."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional, Tuple
from uuid import UUID

import asyncpg
from asyncpg import exceptions as apg_exceptions
import httpx

from .. import crud
from ..config import Settings
from ..utils.partition import target_node_for_quantity

_LOGGER = logging.getLogger(__name__)
_REMOTE_DB_TIMEOUT = 1.0
_REMOTE_HTTP_TIMEOUT = 1.0


@dataclass
class PartitionDecision:
    mode: str  # apply, skip, attempt
    path: str
    quantity: Optional[int]
    resolved_target: Optional[str]
    reason: Optional[str] = None

    def with_reason(self, reason: str) -> PartitionDecision:
        return PartitionDecision(self.mode, self.path, self.quantity, self.resolved_target, reason)


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
                decision = await self._partition_decision(conn, op)
                if decision.mode == "skip":
                    await self.crud.mark_op_applied(conn, op.op_id)
                    self.skipped_count += 1
                    self._log_decision(op, decision, "SKIP")
                    continue
                try:
                    await self.crud.apply_op_tx(conn, op)
                    await self.crud.insert_ack(conn, op.op_id, self.settings.node_name)
                    self.applied_count += 1
                    self._log_decision(op, decision, "APPLY")
                except apg_exceptions.CheckViolationError as exc:
                    await self.crud.mark_op_applied(conn, op.op_id)
                    self.skipped_count += 1
                    self._log_decision(op, decision.with_reason(f"constraint_violation: {exc}"), "SKIP")
                    continue
                except Exception as exc:  # pragma: no cover - exercised via integration tests
                    _LOGGER.exception("Failed to apply op %s", op.op_id)
                    self.last_error = str(exc)
                    return
            self.last_error = None

    def _local_node(self) -> str:
        return self.settings.node_name.lower()

    def _is_master(self) -> bool:
        return self.settings.node_name == self.settings.default_master

    async def _partition_decision(self, conn, op) -> PartitionDecision:
        """Choose how to handle an op based on the deterministic ruleset."""

        # Root cause: previously we only looked at inline payload quantities, so
        # missing or malformed metadata caused shard nodes to skip legitimate ops.
        if self._is_master():
            return PartitionDecision("apply", "master", self._extract_quantity(op.payload or {}), self._local_node())
        payload = op.payload or {}
        target_node = payload.get("target_node") or payload.get("target_partition")
        if target_node:
            target_lower = str(target_node).lower()
            if target_lower == self._local_node():
                return PartitionDecision("apply", "target_node", self._extract_quantity(payload), target_lower)
            return PartitionDecision("skip", "target_node", self._extract_quantity(payload), target_lower, "target_node_mismatch")
        quantity = self._extract_quantity(payload)
        if quantity is not None:
            return self._decision_from_quantity(quantity, "payload_quantity")
        quantity = await self._lookup_local_quantity(conn, op.row_id)
        if quantity is not None:
            return self._decision_from_quantity(quantity, "local_lookup")
        quantity = await self._lookup_remote_quantity(op.row_id)
        if quantity is not None:
            return self._decision_from_quantity(quantity, "remote_lookup")
        return PartitionDecision("attempt", "apply_and_catch", None, None, "quantity_unresolved")

    def _decision_from_quantity(self, quantity: int, path: str) -> PartitionDecision:
        target = target_node_for_quantity(quantity, self.settings.partition_rule)
        if target == self._local_node():
            return PartitionDecision("apply", path, quantity, target)
        return PartitionDecision("skip", path, quantity, target, "partition_mismatch")

    async def _lookup_local_quantity(self, conn, row_id: UUID) -> Optional[int]:
        row = await conn.fetchrow("SELECT quantity FROM orders WHERE order_id=$1", row_id)
        return int(row["quantity"]) if row else None

    async def _lookup_remote_quantity(self, row_id: UUID) -> Optional[int]:
        quantity, succeeded = await self._lookup_remote_quantity_db(row_id)
        if quantity is not None or succeeded:
            return quantity
        return await self._lookup_remote_quantity_http(row_id)

    async def _lookup_remote_quantity_db(self, row_id: UUID) -> Tuple[Optional[int], bool]:
        if not self.settings.node0_dsn:
            return None, False
        try:
            conn = await asyncpg.connect(dsn=self.settings.node0_dsn, timeout=_REMOTE_DB_TIMEOUT)
            try:
                row = await conn.fetchrow("SELECT quantity FROM orders WHERE order_id=$1", row_id, timeout=_REMOTE_DB_TIMEOUT)
                if row:
                    return int(row["quantity"]), True
                return None, True
            finally:
                await conn.close()
        except Exception as exc:  # pragma: no cover - relies on network/DB failures
            _LOGGER.debug("Remote DB lookup failed for %s: %s", row_id, exc)
            return None, False

    async def _lookup_remote_quantity_http(self, row_id: UUID) -> Optional[int]:
        if not self.settings.default_master_url:
            return None
        url = f"{self.settings.default_master_url}/orders/{row_id}?local=true"
        try:
            async with httpx.AsyncClient(timeout=_REMOTE_HTTP_TIMEOUT) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
                if not data:
                    return None
                quantity = data.get("quantity")
                return int(quantity) if quantity is not None else None
        except Exception as exc:  # pragma: no cover - exercised when master HTTP is unavailable
            _LOGGER.debug("Remote HTTP lookup failed for %s: %s", row_id, exc)
        return None

    @staticmethod
    def _extract_quantity(payload: dict) -> Optional[int]:
        value = payload.get("quantity")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _log_decision(self, op, decision: PartitionDecision, outcome: str) -> None:
        _LOGGER.debug(
            "applier_decision op=%s origin=%s type=%s path=%s target=%s quantity=%s outcome=%s reason=%s",
            op.op_id,
            op.origin_node,
            op.op_type,
            decision.path,
            decision.resolved_target or "unknown",
            decision.quantity,
            outcome,
            decision.reason,
        )

    def metrics(self) -> dict:
        return {
            "applied_count": self.applied_count,
            "skipped_count": self.skipped_count,
            "last_error": self.last_error,
        }
