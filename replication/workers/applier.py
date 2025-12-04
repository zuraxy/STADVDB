"""Op-log applier worker."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from uuid import UUID, uuid4

import asyncpg
from asyncpg import exceptions as apg_exceptions
import httpx

from .. import crud
from ..config import Settings
from ..utils.partition import target_node_for_quantity

_LOGGER = logging.getLogger(__name__)
_REMOTE_DB_TIMEOUT = 1.0
_REMOTE_HTTP_TIMEOUT = 1.0
_REMOTE_RETRY_DELAYS = (0.2, 0.4)


@dataclass
class PartitionDecision:
    mode: str  # apply, skip, retry
    path: str
    quantity: Optional[int]
    resolved_target: Optional[str]
    reason: Optional[str] = None

    def with_reason(self, reason: str) -> PartitionDecision:
        return PartitionDecision(self.mode, self.path, self.quantity, self.resolved_target, reason)


class ApplierWorker:
    """Continuously applies unapplied operations with partition awareness."""

    def __init__(self, pool, settings: Settings, crud_module=crud, worker_id: Optional[str] = None, is_paused: Optional[callable] = None, is_leader: Optional[callable] = None) -> None:
        self.pool = pool
        self.settings = settings
        self.crud = crud_module
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self.applied_count = 0
        self.skipped_count = 0
        self.failed_count = 0
        self.retry_count = 0
        self.applier_attempts = 0
        self.last_error: Optional[str] = None
        self.worker_id = worker_id or f"applier-{uuid4().hex[:8]}"
        self._attempts: Dict[UUID, int] = {}
        self._cursor_cache: Dict[str, int] = {}
        self._cursor_loaded = False
        self._max_attempts = max(1, self.settings.applier_max_attempts)
        self._is_paused = is_paused  # Callback to check if worker should pause
        self._is_leader_cb = is_leader  # Callback to check if this node is current leader

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
        await self._refresh_cursor_cache()
        while not self._stop_event.is_set():
            await self.apply_once()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.settings.applier_interval)
            except asyncio.TimeoutError:
                continue

    async def apply_once(self) -> None:
        # Skip processing if node is paused (simulated as down)
        if self._is_paused and self._is_paused():
            _LOGGER.debug("APPLIER: Skipping - node is paused")
            return
        
        _LOGGER.info("APPLIER: apply_once starting, node=%s is_master=%s", self._local_node(), self._is_master())
        await self._refresh_cursor_cache()
        async with self.pool.acquire() as conn:
            while True:
                retry_requested = False
                async with conn.transaction():
                    op = await self._next_locked_op(conn)
                    if not op:
                        _LOGGER.info("APPLIER: No unapplied ops found")
                        self.last_error = None
                        return
                    _LOGGER.info("APPLIER: Processing op=%s lamport=%s origin=%s", op.op_id, op.lamport, op.origin_node)
                    outcome = await self._process_locked_op(conn, op)
                    _LOGGER.info("APPLIER: Outcome for op=%s: %s", op.op_id, outcome)
                    if outcome == "retry":
                        retry_requested = True
                        self.retry_count += 1
                        self._debug("retrying op %s after releasing lock", op.op_id)
                if retry_requested:
                    await asyncio.sleep(_REMOTE_RETRY_DELAYS[0])

    async def _next_locked_op(self, conn):
        ops = await self.crud.fetch_unapplied_ops(conn, limit=1)
        return ops[0] if ops else None

    async def _process_locked_op(self, conn, op) -> str:
        attempt = self._increment_attempt(op.op_id)
        decision = await self._partition_decision(conn, op, attempt)
        if decision.mode == "retry":
            self._log_decision(op, decision, "RETRY", attempt)
            return "retry"
        if decision.mode == "skip":
            if op.op_type != "delete" and decision.reason in {"partition_mismatch", "target_node_mismatch"}:
                await self._purge_local_row(conn, op.row_id)
            await self.crud.mark_op_applied(conn, op.op_id)
            await self.crud.insert_ack(conn, op.op_id, self.settings.node_name)
            self.skipped_count += 1
            self._clear_attempt(op.op_id)
            self._log_decision(op, decision, "SKIP", attempt)
            return "skip"
        try:
            await self.crud.apply_op_tx(conn, op, use_transaction=False)
            await self.crud.insert_ack(conn, op.op_id, self.settings.node_name)
            self.applied_count += 1
            self._clear_attempt(op.op_id)
            self.last_error = None
            self._log_decision(op, decision, "APPLY", attempt)
            return "apply"
        except apg_exceptions.CheckViolationError as exc:
            await self.crud.mark_op_applied(conn, op.op_id)
            await self.crud.insert_ack(conn, op.op_id, self.settings.node_name)
            self.skipped_count += 1
            self._clear_attempt(op.op_id)
            self._log_decision(op, decision.with_reason(f"constraint_violation: {exc}"), "SKIP", attempt)
            return "skip"
        except Exception as exc:  # pragma: no cover - defensive guard
            self.failed_count += 1
            self.last_error = str(exc)
            self._log_decision(op, decision.with_reason(str(exc)), "ERROR", attempt)
            raise

    def _increment_attempt(self, op_id: UUID) -> int:
        self.applier_attempts += 1
        self._attempts[op_id] = self._attempts.get(op_id, 0) + 1
        return self._attempts[op_id]

    def _clear_attempt(self, op_id: UUID) -> None:
        self._attempts.pop(op_id, None)

    async def _partition_decision(self, conn, op, attempt: int) -> PartitionDecision:
        _LOGGER.info(
            "APPLIER_DEBUG: Processing op=%s type=%s origin=%s payload=%s local_node=%s is_master=%s",
            op.op_id, op.op_type, op.origin_node, op.payload, self._local_node(), self._is_master()
        )
        if op.op_type == "delete":
            return PartitionDecision("apply", "delete", None, self._local_node())
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
        _LOGGER.info("APPLIER_DEBUG: Extracted quantity=%s from payload", quantity)
        if quantity is not None:
            decision = self._decision_from_quantity(quantity, "payload_quantity")
            _LOGGER.info("APPLIER_DEBUG: Decision from quantity: mode=%s target=%s", decision.mode, decision.resolved_target)
            return decision
        quantity = await self._lookup_local_quantity(conn, op.row_id)
        if quantity is not None:
            return self._decision_from_quantity(quantity, "local_lookup")
        quantity, status = await self._lookup_remote_quantity(op.row_id)
        if status == "ok" and quantity is not None:
            return self._decision_from_quantity(quantity, "remote_lookup")
        if status == "error" and attempt < self._max_attempts:
            return PartitionDecision("retry", "remote_lookup", None, None, "remote_lookup_failed")
        return PartitionDecision("apply", "apply_and_catch", None, None, "quantity_unresolved")

    def _decision_from_quantity(self, quantity: int, path: str) -> PartitionDecision:
        target = target_node_for_quantity(quantity, self.settings.partition_rule)
        if target == self._local_node():
            return PartitionDecision("apply", path, quantity, target)
        return PartitionDecision("skip", path, quantity, target, "partition_mismatch")

    async def _lookup_local_quantity(self, conn, row_id: UUID) -> Optional[int]:
        row = await conn.fetchrow("SELECT quantity FROM orders WHERE order_id=$1", row_id)
        return int(row["quantity"]) if row else None

    async def _lookup_remote_quantity(self, row_id: UUID) -> Tuple[Optional[int], str]:
        quantity, status = await self._lookup_remote_quantity_db(row_id)
        if status in {"ok", "not_found"}:
            return quantity, status
        quantity, status = await self._lookup_remote_quantity_http(row_id)
        return quantity, status

    async def _lookup_remote_quantity_db(self, row_id: UUID) -> Tuple[Optional[int], str]:
        if not self.settings.node0_dsn:
            return None, "error"
        for attempt, delay in enumerate((0.0, *_REMOTE_RETRY_DELAYS), start=1):
            if delay:
                await asyncio.sleep(delay)
            try:
                conn = await asyncpg.connect(dsn=self.settings.node0_dsn, timeout=_REMOTE_DB_TIMEOUT)
                try:
                    row = await conn.fetchrow("SELECT quantity FROM orders WHERE order_id=$1", row_id, timeout=_REMOTE_DB_TIMEOUT)
                    if row:
                        self._debug("remote_db quantity hit op=%s attempt=%s", row_id, attempt)
                        return int(row["quantity"]), "ok"
                    self._debug("remote_db quantity miss op=%s attempt=%s", row_id, attempt)
                    return None, "not_found"
                finally:
                    await conn.close()
            except Exception as exc:  # pragma: no cover - network/DB failures
                self._debug("remote_db lookup failure op=%s attempt=%s err=%s", row_id, attempt, exc)
        return None, "error"

    async def _lookup_remote_quantity_http(self, row_id: UUID) -> Tuple[Optional[int], str]:
        if not self.settings.default_master_url:
            return None, "error"
        url = f"{self.settings.default_master_url}/orders/{row_id}?local=true"
        async with httpx.AsyncClient(timeout=_REMOTE_HTTP_TIMEOUT) as client:
            for attempt, delay in enumerate((0.0, *_REMOTE_RETRY_DELAYS), start=1):
                if delay:
                    await asyncio.sleep(delay)
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    data = response.json()
                    if not data:
                        return None, "not_found"
                    quantity = data.get("quantity")
                    return (int(quantity) if quantity is not None else None), "ok"
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 404:
                        return None, "not_found"
                    self._debug("remote_http status_err op=%s attempt=%s err=%s", row_id, attempt, exc)
                except Exception as exc:  # pragma: no cover - HTTP client issues
                    self._debug("remote_http lookup failure op=%s attempt=%s err=%s", row_id, attempt, exc)
        return None, "error"

    def _local_node(self) -> str:
        return self.settings.node_name.lower()

    def _is_master(self) -> bool:
        """Check if this node is the current leader/master.
        
        Uses the is_leader callback if available (checks ClusterManager's current_leader),
        otherwise falls back to checking if this is the default_master.
        """
        if self._is_leader_cb:
            return self._is_leader_cb()
        return self.settings.node_name == self.settings.default_master

    @staticmethod
    def _extract_quantity(payload: dict) -> Optional[int]:
        value = payload.get("quantity")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _log_decision(self, op, decision: PartitionDecision, outcome: str, attempt: int) -> None:
        if not self.settings.applier_debug:
            return
        last_seen = self._cursor_cache.get(op.origin_node.lower(), -1)
        _LOGGER.debug(
            "applier_decision op=%s lamport=%s last_seen=%s attempts=%s worker=%s locked=%s path=%s target=%s quantity=%s outcome=%s reason=%s",
            op.op_id,
            op.lamport,
            last_seen,
            attempt,
            self.worker_id,
            True,
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
            "failed_count": self.failed_count,
            "retry_count": self.retry_count,
            "applier_attempts": self.applier_attempts,
            "last_error": self.last_error,
        }

    async def _refresh_cursor_cache(self) -> None:
        if self._cursor_loaded:
            return
        async with self.pool.acquire() as conn:
            rows = await self.crud.load_replication_cursors(conn)
            self._cursor_cache = {name.lower(): value for name, value in rows.items()}
        self._cursor_loaded = True

    def _debug(self, message: str, *args) -> None:
        if self.settings.applier_debug:
            _LOGGER.debug(message, *args)

    async def _purge_local_row(self, conn, row_id: UUID) -> None:
        await conn.execute("DELETE FROM orders WHERE order_id=$1", row_id)
        self._debug("purged local row=%s due to partition mismatch", row_id)
