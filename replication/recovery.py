"""Recovery manager for leader, node, and promotion recovery flows."""

from __future__ import annotations

import asyncio
import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from uuid import UUID, uuid4

from . import crud
from .config import Settings, PeerNode
from .models import OpRecord
from .utils.http_client import HTTPClient

_LOGGER = logging.getLogger(__name__)

# Recovery constants
SNAPSHOT_GAP_THRESHOLD = 10000  # If gap exceeds this, trigger snapshot fallback
BATCH_SIZE = 500  # Ops to fetch per request
APPLY_BATCH_SIZE = 100  # Ops to apply in one transaction batch


class RecoveryState(str, Enum):
    """Recovery job state machine states."""
    PENDING = "pending"
    STARTUP = "startup"
    SYNCING = "syncing"
    NEEDS_REBUILD = "needs_rebuild"
    APPLYING = "applying"
    GATING = "gating"
    READY = "ready"
    FAILED = "failed"
    ABORTED = "aborted"


class RecoveryMode(str, Enum):
    """Types of recovery operations."""
    LEADER = "leader"
    NODE = "node"
    PROMOTION = "promotion"


@dataclass
class RecoveryMetrics:
    """Progress metrics for a recovery job."""
    last_applied_lamport: int = -1
    ops_fetched: int = 0
    ops_applied: int = 0
    ops_remaining: int = 0
    conflicts_detected: int = 0
    snapshots_imported: int = 0
    peers_contacted: int = 0
    peers_failed: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    @property
    def apply_rate(self) -> float:
        """Ops applied per second."""
        if not self.start_time:
            return 0.0
        elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        if elapsed <= 0:
            return 0.0
        return self.ops_applied / elapsed
    
    @property
    def estimated_eta_seconds(self) -> Optional[float]:
        """Estimated seconds to completion."""
        if self.ops_remaining <= 0:
            return 0.0
        rate = self.apply_rate
        if rate <= 0:
            return None
        return self.ops_remaining / rate
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "last_applied_lamport": self.last_applied_lamport,
            "ops_fetched": self.ops_fetched,
            "ops_applied": self.ops_applied,
            "ops_remaining": self.ops_remaining,
            "conflicts_detected": self.conflicts_detected,
            "snapshots_imported": self.snapshots_imported,
            "peers_contacted": self.peers_contacted,
            "peers_failed": self.peers_failed,
            "apply_rate": round(self.apply_rate, 2),
            "estimated_eta_seconds": self.estimated_eta_seconds,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }


@dataclass
class RecoveryLogEntry:
    """Single log entry for recovery job."""
    timestamp: datetime
    level: str
    message: str
    details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level,
            "message": self.message,
            "details": self.details or {},
        }


@dataclass
class RecoveryJob:
    """State container for a recovery job."""
    job_id: str
    mode: RecoveryMode
    state: RecoveryState = RecoveryState.PENDING
    metrics: RecoveryMetrics = field(default_factory=RecoveryMetrics)
    logs: List[RecoveryLogEntry] = field(default_factory=list)
    since_ts: Optional[datetime] = None
    promoted_node: Optional[str] = None
    error: Optional[str] = None
    _task: Optional[asyncio.Task] = field(default=None, repr=False)
    _abort_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    _log_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    
    def log(self, level: str, message: str, **details: Any) -> None:
        """Add a log entry (synchronous for simplicity)."""
        entry = RecoveryLogEntry(
            timestamp=datetime.now(timezone.utc),
            level=level,
            message=message,
            details=details if details else None,
        )
        self.logs.append(entry)
        log_fn = getattr(_LOGGER, level.lower(), _LOGGER.info)
        log_fn("Recovery[%s]: %s %s", self.job_id[:8], message, details or "")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "mode": self.mode.value,
            "state": self.state.value,
            "metrics": self.metrics.to_dict(),
            "since_ts": self.since_ts.isoformat() if self.since_ts else None,
            "promoted_node": self.promoted_node,
            "error": self.error,
        }


class RecoveryManager:
    """Manages recovery operations for the node."""
    
    def __init__(
        self,
        pool,
        settings: Settings,
        http_client: Optional[HTTPClient] = None,
        crud_module=crud,
        get_promoted_flag: Optional[Callable[[], bool]] = None,
    ) -> None:
        self.pool = pool
        self.settings = settings
        self.http_client = http_client or HTTPClient()
        self.crud = crud_module
        self._get_promoted_flag = get_promoted_flag or (lambda: False)
        self._jobs: Dict[str, RecoveryJob] = {}
        self._active_job: Optional[str] = None
        self._lock = asyncio.Lock()
        self._recovery_flag = False  # When True, writes are gated
    
    @property
    def recovery_in_progress(self) -> bool:
        """Check if any recovery is currently running."""
        return self._active_job is not None
    
    @property
    def writes_gated(self) -> bool:
        """Check if writes should be blocked."""
        return self._recovery_flag
    
    def set_recovery_flag(self, flag: bool) -> None:
        """Set the recovery flag to gate writes."""
        self._recovery_flag = flag
        _LOGGER.info("Recovery flag set to %s", flag)
    
    async def start_job(
        self,
        mode: str,
        since_ts: Optional[str] = None,
        promoted_node: Optional[str] = None,
    ) -> str:
        """Start a new recovery job."""
        async with self._lock:
            if self._active_job:
                raise RuntimeError(f"Recovery job {self._active_job} already in progress")
            
            job_id = str(uuid4())
            parsed_ts = None
            if since_ts:
                try:
                    parsed_ts = datetime.fromisoformat(since_ts.replace("Z", "+00:00"))
                except ValueError:
                    raise ValueError(f"Invalid since_ts format: {since_ts}")
            
            job = RecoveryJob(
                job_id=job_id,
                mode=RecoveryMode(mode),
                since_ts=parsed_ts,
                promoted_node=promoted_node,
            )
            job.metrics.start_time = datetime.now(timezone.utc)
            self._jobs[job_id] = job
            self._active_job = job_id
            
            # Start the recovery task
            if job.mode == RecoveryMode.LEADER:
                job._task = asyncio.create_task(self._run_leader_recovery(job))
            elif job.mode == RecoveryMode.NODE:
                job._task = asyncio.create_task(self._run_node_rejoin(job))
            elif job.mode == RecoveryMode.PROMOTION:
                job._task = asyncio.create_task(self._run_promotion_resync(job))
            
            job.log("info", f"Started {mode} recovery job", job_id=job_id)
            return job_id
    
    def get_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get current status of a recovery job."""
        job = self._jobs.get(job_id)
        return job.to_dict() if job else None
    
    def get_logs(self, job_id: str, limit: int = 100) -> Optional[List[Dict[str, Any]]]:
        """Get logs for a recovery job."""
        job = self._jobs.get(job_id)
        if not job:
            return None
        return [entry.to_dict() for entry in job.logs[-limit:]]
    
    async def abort_job(self, job_id: str) -> bool:
        """Abort a running recovery job."""
        job = self._jobs.get(job_id)
        if not job:
            return False
        
        job._abort_event.set()
        if job._task and not job._task.done():
            job._task.cancel()
            try:
                await job._task
            except asyncio.CancelledError:
                pass
        
        job.state = RecoveryState.ABORTED
        job.metrics.end_time = datetime.now(timezone.utc)
        job.log("warning", "Job aborted by user")
        
        async with self._lock:
            if self._active_job == job_id:
                self._active_job = None
                self._recovery_flag = False
        
        return True
    
    async def _run_leader_recovery(self, job: RecoveryJob) -> None:
        """Execute leader recovery flow."""
        try:
            job.state = RecoveryState.STARTUP
            job.log("info", "Starting leader recovery")
            
            # Step 1: Get local watermark
            local_max = await self._get_local_max_lamport()
            job.metrics.last_applied_lamport = local_max
            job.log("info", f"Local max lamport: {local_max}")
            
            # Step 2: Check if we need full rebuild
            needs_snapshot = await self._check_needs_snapshot(job, local_max)
            
            if needs_snapshot:
                job.state = RecoveryState.NEEDS_REBUILD
                job.log("warning", "Gap exceeds threshold, initiating snapshot rebuild")
                await self._snapshot_rebuild(job)
                local_max = await self._get_local_max_lamport()
                job.metrics.last_applied_lamport = local_max
            
            # Step 3: Incremental sync
            job.state = RecoveryState.SYNCING
            self.set_recovery_flag(True)  # Gate writes during sync
            
            await self._incremental_sync(job, local_max)
            
            # Step 4: Apply all unapplied ops
            job.state = RecoveryState.APPLYING
            await self._apply_all_pending(job)
            
            # Step 5: Bump lamport clock
            await self._bump_lamport_ceiling(job)
            
            # Step 6: Verify consistency
            conflicts = await self._verify_consistency(job)
            job.metrics.conflicts_detected = conflicts
            
            # Step 7: Final gating period
            job.state = RecoveryState.GATING
            job.log("info", "Entering gating period (1s quiesce)")
            await asyncio.sleep(1.0)
            
            # Step 8: Ready
            job.state = RecoveryState.READY
            job.metrics.end_time = datetime.now(timezone.utc)
            self.set_recovery_flag(False)
            job.log("info", "Leader recovery completed successfully")
            
        except asyncio.CancelledError:
            job.state = RecoveryState.ABORTED
            job.log("warning", "Leader recovery aborted")
            raise
        except Exception as e:
            job.state = RecoveryState.FAILED
            job.error = str(e)
            job.log("error", f"Leader recovery failed: {e}")
            _LOGGER.exception("Leader recovery failed")
        finally:
            self.set_recovery_flag(False)
            job.metrics.end_time = datetime.now(timezone.utc)
            async with self._lock:
                if self._active_job == job.job_id:
                    self._active_job = None
    
    async def _run_node_rejoin(self, job: RecoveryJob) -> None:
        """Execute node cold-rejoin flow."""
        try:
            job.state = RecoveryState.SYNCING
            job.log("info", "Starting node rejoin")
            
            # Get local max lamport
            local_max = await self._get_local_max_lamport()
            job.metrics.last_applied_lamport = local_max
            job.log("info", f"Local max lamport: {local_max}")
            
            # Check if gap requires snapshot
            needs_snapshot = await self._check_needs_snapshot(job, local_max)
            
            if needs_snapshot:
                job.state = RecoveryState.NEEDS_REBUILD
                # For node rejoin, only fetch our partition
                partition = self._get_local_partition()
                await self._import_partition_snapshot(job, partition)
                local_max = await self._get_local_max_lamport()
            
            # Incremental sync
            job.state = RecoveryState.SYNCING
            await self._incremental_sync(job, local_max)
            
            # Apply pending ops
            job.state = RecoveryState.APPLYING
            await self._apply_all_pending(job)
            
            job.state = RecoveryState.READY
            job.metrics.end_time = datetime.now(timezone.utc)
            job.log("info", "Node rejoin completed successfully")
            
        except asyncio.CancelledError:
            job.state = RecoveryState.ABORTED
            raise
        except Exception as e:
            job.state = RecoveryState.FAILED
            job.error = str(e)
            job.log("error", f"Node rejoin failed: {e}")
        finally:
            job.metrics.end_time = datetime.now(timezone.utc)
            async with self._lock:
                if self._active_job == job.job_id:
                    self._active_job = None
    
    async def _run_promotion_resync(self, job: RecoveryJob) -> None:
        """Execute promotion resync flow (Node0 catching up after promoted nodes wrote)."""
        try:
            job.state = RecoveryState.SYNCING
            self.set_recovery_flag(True)
            job.log("info", f"Starting promotion resync from {job.promoted_node}")
            
            # Fetch ops from promoted period only
            if job.since_ts:
                await self._fetch_promotion_ops(job)
            else:
                # Fallback to full sync if no timestamp
                local_max = await self._get_local_max_lamport()
                await self._incremental_sync(job, local_max)
            
            # Apply ops
            job.state = RecoveryState.APPLYING
            await self._apply_all_pending(job)
            
            # Broadcast demotion to promoted nodes
            await self._broadcast_demotion(job)
            
            job.state = RecoveryState.READY
            job.metrics.end_time = datetime.now(timezone.utc)
            self.set_recovery_flag(False)
            job.log("info", "Promotion resync completed successfully")
            
        except asyncio.CancelledError:
            job.state = RecoveryState.ABORTED
            raise
        except Exception as e:
            job.state = RecoveryState.FAILED
            job.error = str(e)
            job.log("error", f"Promotion resync failed: {e}")
        finally:
            self.set_recovery_flag(False)
            job.metrics.end_time = datetime.now(timezone.utc)
            async with self._lock:
                if self._active_job == job.job_id:
                    self._active_job = None
    
    async def _get_local_max_lamport(self) -> int:
        """Get the maximum lamport value from local op_log."""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT COALESCE(MAX(lamport), -1) FROM op_log"
            )
            return int(result)
    
    async def _check_needs_snapshot(self, job: RecoveryJob, local_max: int) -> bool:
        """Check if any peer's max lamport exceeds our threshold."""
        if local_max < 0:
            job.log("info", "Empty local op_log, snapshot required")
            return True
        
        for peer in self.settings.peer_nodes:
            if peer.name == self.settings.node_name:
                continue
            try:
                peer_max = await self._get_peer_max_lamport(peer)
                gap = peer_max - local_max
                if gap > SNAPSHOT_GAP_THRESHOLD:
                    job.log("warning", f"Gap with {peer.name} is {gap}, exceeds threshold")
                    return True
                job.metrics.peers_contacted += 1
            except Exception as e:
                job.log("warning", f"Failed to contact {peer.name}: {e}")
                job.metrics.peers_failed += 1
        
        return False
    
    async def _get_peer_max_lamport(self, peer: PeerNode) -> int:
        """Get max lamport from a peer's oplog."""
        # Fetch a single op with highest lamport
        try:
            ops = await self.http_client.get_json(
                f"{peer.base_url}/oplog",
                params={"since_lamport": -1, "limit": 1}
            )
            if ops:
                return max(op.get("lamport", 0) for op in ops)
            return 0
        except Exception:
            return 0
    
    async def _incremental_sync(self, job: RecoveryJob, since_lamport: int) -> None:
        """Fetch and store ops from all peers incrementally."""
        job.log("info", f"Starting incremental sync from lamport {since_lamport}")
        
        current_lamport = since_lamport
        total_fetched = 0
        
        while not job._abort_event.is_set():
            fetched_this_round = 0
            
            for peer in self.settings.peer_nodes:
                if peer.name == self.settings.node_name:
                    continue
                if job._abort_event.is_set():
                    break
                
                try:
                    ops = await self._fetch_ops_from_peer(peer, current_lamport)
                    if ops:
                        await self._store_ops(ops)
                        fetched_this_round += len(ops)
                        max_lamport = max(op.lamport for op in ops)
                        current_lamport = max(current_lamport, max_lamport)
                        job.metrics.ops_fetched += len(ops)
                        job.log("debug", f"Fetched {len(ops)} ops from {peer.name}")
                except Exception as e:
                    job.log("warning", f"Error fetching from {peer.name}: {e}")
            
            total_fetched += fetched_this_round
            
            if fetched_this_round == 0:
                break  # No more ops to fetch
            
            # Update metrics
            job.metrics.last_applied_lamport = current_lamport
        
        job.log("info", f"Incremental sync complete, fetched {total_fetched} total ops")
    
    async def _fetch_ops_from_peer(
        self,
        peer: PeerNode,
        since_lamport: int,
    ) -> List[OpRecord]:
        """Fetch ops from a peer's /oplog endpoint."""
        try:
            data = await self.http_client.get_json(
                f"{peer.base_url}/oplog",
                params={"since_lamport": since_lamport, "limit": BATCH_SIZE}
            )
            return [OpRecord(**item) for item in data]
        except Exception as e:
            _LOGGER.warning("Failed to fetch ops from %s: %s", peer.base_url, e)
            raise
    
    async def _store_ops(self, ops: List[OpRecord]) -> int:
        """Store ops in local op_log, deduplicating by op_id."""
        inserted = 0
        async with self.pool.acquire() as conn:
            # Sort by (lamport, origin_node) for proper ordering
            sorted_ops = sorted(ops, key=lambda o: (o.lamport, o.origin_node))
            for op in sorted_ops:
                try:
                    was_new = await self.crud.insert_op_if_missing(conn, op)
                    if was_new:
                        inserted += 1
                except Exception as e:
                    _LOGGER.warning("Failed to insert op %s: %s", op.op_id, e)
        return inserted
    
    async def _apply_all_pending(self, job: RecoveryJob) -> None:
        """Apply all unapplied ops in lamport order."""
        job.log("info", "Applying pending operations")
        
        applied_count = 0
        async with self.pool.acquire() as conn:
            while not job._abort_event.is_set():
                # Fetch batch of unapplied ops
                ops = await self.crud.fetch_unapplied_ops(conn, limit=APPLY_BATCH_SIZE)
                if not ops:
                    break
                
                job.metrics.ops_remaining = len(ops)
                
                for op in ops:
                    if job._abort_event.is_set():
                        break
                    try:
                        async with conn.transaction():
                            await self.crud.apply_op_tx(conn, op, use_transaction=False)
                            await self.crud.insert_ack(conn, op.op_id, self.settings.node_name)
                        applied_count += 1
                        job.metrics.ops_applied += 1
                    except Exception as e:
                        job.log("warning", f"Failed to apply op {op.op_id}: {e}")
        
        job.metrics.ops_remaining = 0
        job.log("info", f"Applied {applied_count} operations")
    
    async def _bump_lamport_ceiling(self, job: RecoveryJob) -> None:
        """Ensure local lamport clock is ahead of all received ops."""
        job.log("info", "Bumping lamport clock ceiling")
        
        async with self.pool.acquire() as conn:
            max_lamport = await conn.fetchval(
                "SELECT COALESCE(MAX(lamport), 0) FROM op_log"
            )
            # Ensure node_metadata table exists
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS node_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            # Store ceiling with buffer
            ceiling = int(max_lamport) + 1000
            await conn.execute("""
                INSERT INTO node_metadata (key, value, updated_at)
                VALUES ('lamport_ceiling', $1, NOW())
                ON CONFLICT (key) DO UPDATE SET value = $1, updated_at = NOW()
            """, str(ceiling))
        
        job.log("info", f"Lamport ceiling set to {ceiling}")
    
    async def _verify_consistency(self, job: RecoveryJob) -> int:
        """Check for duplicate order_ids and other consistency issues."""
        job.log("info", "Verifying data consistency")
        
        async with self.pool.acquire() as conn:
            # Check for duplicate order_ids
            duplicates = await conn.fetch("""
                SELECT order_id, COUNT(*) as cnt
                FROM orders
                GROUP BY order_id
                HAVING COUNT(*) > 1
            """)
            
            if duplicates:
                job.log("error", f"Found {len(duplicates)} duplicate order_ids")
                for dup in duplicates:
                    job.log("error", f"Duplicate: {dup['order_id']} ({dup['cnt']} copies)")
            
            return len(duplicates)
    
    async def _snapshot_rebuild(self, job: RecoveryJob) -> None:
        """Full snapshot rebuild from peers."""
        job.log("info", "Initiating full snapshot rebuild")
        
        # For leader node, we need data from all partitions
        for peer in self.settings.peer_nodes:
            if peer.name == self.settings.node_name:
                continue
            
            try:
                await self._import_peer_snapshot(job, peer)
                job.metrics.snapshots_imported += 1
            except Exception as e:
                job.log("error", f"Failed to import snapshot from {peer.name}: {e}")
    
    async def _import_partition_snapshot(self, job: RecoveryJob, partition: str) -> None:
        """Import snapshot for a specific partition."""
        job.log("info", f"Importing snapshot for partition {partition}")
        
        # Find peer that has this partition
        for peer in self.settings.peer_nodes:
            if peer.name == self.settings.node_name:
                continue
            try:
                await self._import_peer_snapshot(job, peer, partition=partition)
                job.metrics.snapshots_imported += 1
                return
            except Exception as e:
                job.log("warning", f"Failed to get snapshot from {peer.name}: {e}")
        
        job.log("error", f"Could not get snapshot for partition {partition}")
    
    async def _import_peer_snapshot(
        self,
        job: RecoveryJob,
        peer: PeerNode,
        partition: Optional[str] = None,
    ) -> None:
        """Request and import snapshot from a peer."""
        job.log("info", f"Requesting snapshot from {peer.name}")
        
        try:
            # Request snapshot
            params = {"partition": partition} if partition else {}
            response = await self.http_client.get_json(
                f"{peer.base_url}/recovery/snapshot",
                params=params
            )
            
            if "data" in response:
                await self._import_snapshot_data(response["data"])
                job.log("info", f"Imported {len(response['data'])} rows from {peer.name}")
            elif "csv" in response:
                await self._import_snapshot_csv(response["csv"])
                job.log("info", f"Imported CSV snapshot from {peer.name}")
                
        except Exception as e:
            job.log("error", f"Snapshot import from {peer.name} failed: {e}")
            raise
    
    async def _import_snapshot_data(self, rows: List[Dict[str, Any]]) -> None:
        """Import snapshot data rows."""
        import json
        async with self.pool.acquire() as conn:
            for row in rows:
                payload_json = json.dumps(row.get("payload") or {})
                await conn.execute("""
                    INSERT INTO orders (order_id, quantity, payload, created_at, updated_at)
                    VALUES ($1, $2, $3::jsonb, $4, $5)
                    ON CONFLICT (order_id) DO UPDATE SET
                        quantity = EXCLUDED.quantity,
                        payload = EXCLUDED.payload,
                        updated_at = EXCLUDED.updated_at
                """,
                    UUID(row["order_id"]) if isinstance(row["order_id"], str) else row["order_id"],
                    row["quantity"],
                    payload_json,
                    row.get("created_at") or datetime.now(timezone.utc),
                    row.get("updated_at") or datetime.now(timezone.utc),
                )
    
    async def _import_snapshot_csv(self, csv_data: str) -> None:
        """Import snapshot from CSV string."""
        import json
        reader = csv.DictReader(io.StringIO(csv_data))
        async with self.pool.acquire() as conn:
            for row in reader:
                payload_json = row.get("payload", "{}")
                await conn.execute("""
                    INSERT INTO orders (order_id, quantity, payload, created_at, updated_at)
                    VALUES ($1, $2, $3::jsonb, NOW(), NOW())
                    ON CONFLICT (order_id) DO UPDATE SET
                        quantity = EXCLUDED.quantity,
                        payload = EXCLUDED.payload,
                        updated_at = NOW()
                """,
                    UUID(row["order_id"]),
                    int(row["quantity"]),
                    payload_json,
                )
    
    async def _fetch_promotion_ops(self, job: RecoveryJob) -> None:
        """Fetch ops created during promotion period."""
        job.log("info", f"Fetching promotion ops since {job.since_ts}")
        
        for peer in self.settings.peer_nodes:
            if peer.name == self.settings.node_name:
                continue
            
            # We can't filter by timestamp in standard /oplog, so fetch all
            # and filter locally, or extend the endpoint
            try:
                since_ts_iso = job.since_ts.isoformat() if job.since_ts else None
                ops = await self.http_client.get_json(
                    f"{peer.base_url}/oplog",
                    params={
                        "since_lamport": -1,
                        "limit": 10000,
                        "since_ts": since_ts_iso,
                    }
                )
                # Filter ops by timestamp
                filtered = []
                for op_data in ops:
                    ts_str = op_data.get("ts")
                    if ts_str and job.since_ts:
                        op_ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        if op_ts >= job.since_ts:
                            filtered.append(OpRecord(**op_data))
                    else:
                        filtered.append(OpRecord(**op_data))
                
                if filtered:
                    await self._store_ops(filtered)
                    job.metrics.ops_fetched += len(filtered)
                    job.log("info", f"Fetched {len(filtered)} promotion ops from {peer.name}")
                    
            except Exception as e:
                job.log("warning", f"Failed to fetch promotion ops from {peer.name}: {e}")
    
    async def _broadcast_demotion(self, job: RecoveryJob) -> None:
        """Broadcast demotion signal to promoted peers."""
        job.log("info", "Broadcasting demotion to promoted nodes")
        
        for peer in self.settings.peer_nodes:
            if peer.name == self.settings.node_name:
                continue
            try:
                await self.http_client.post_json(
                    f"{peer.base_url}/admin/demote",
                    {"demote": True}
                )
                job.log("info", f"Demoted {peer.name}")
            except Exception as e:
                job.log("warning", f"Failed to demote {peer.name}: {e}")
    
    def _get_local_partition(self) -> str:
        """Determine which partition this node serves."""
        node = self.settings.node_name.lower()
        if node == "node1":
            return "low"  # qty <= partition_rule
        elif node == "node2":
            return "high"  # qty > partition_rule
        return "all"
    
    # Public helpers for snapshot export
    async def export_snapshot(
        self,
        partition: Optional[str] = None,
        format: str = "json",
    ) -> Dict[str, Any]:
        """Export local orders data as snapshot."""
        async with self.pool.acquire() as conn:
            if partition == "low":
                rows = await conn.fetch(
                    "SELECT order_id, quantity, payload, created_at, updated_at "
                    "FROM orders WHERE quantity <= $1",
                    self.settings.partition_rule
                )
            elif partition == "high":
                rows = await conn.fetch(
                    "SELECT order_id, quantity, payload, created_at, updated_at "
                    "FROM orders WHERE quantity > $1",
                    self.settings.partition_rule
                )
            else:
                rows = await conn.fetch(
                    "SELECT order_id, quantity, payload, created_at, updated_at FROM orders"
                )
        
        if format == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["order_id", "quantity", "payload", "created_at", "updated_at"])
            for row in rows:
                import json
                payload_str = json.dumps(row["payload"]) if row["payload"] else "{}"
                writer.writerow([
                    str(row["order_id"]),
                    row["quantity"],
                    payload_str,
                    row["created_at"].isoformat() if row["created_at"] else "",
                    row["updated_at"].isoformat() if row["updated_at"] else "",
                ])
            return {"csv": output.getvalue(), "count": len(rows)}
        
        # JSON format
        data = []
        for row in rows:
            data.append({
                "order_id": str(row["order_id"]),
                "quantity": row["quantity"],
                "payload": row["payload"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
            })
        return {"data": data, "count": len(data)}


# Standalone helper functions for use outside RecoveryManager

async def export_snapshot_helper(
    pool,
    partition: Optional[str] = None,
    partition_rule: int = 5,
) -> Dict[str, Any]:
    """Export orders table as snapshot."""
    async with pool.acquire() as conn:
        if partition == "low":
            rows = await conn.fetch(
                "SELECT order_id, quantity, payload, created_at, updated_at "
                "FROM orders WHERE quantity <= $1",
                partition_rule
            )
        elif partition == "high":
            rows = await conn.fetch(
                "SELECT order_id, quantity, payload, created_at, updated_at "
                "FROM orders WHERE quantity > $1",
                partition_rule
            )
        else:
            rows = await conn.fetch(
                "SELECT order_id, quantity, payload, created_at, updated_at FROM orders"
            )
    
    data = []
    for row in rows:
        data.append({
            "order_id": str(row["order_id"]),
            "quantity": row["quantity"],
            "payload": row["payload"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        })
    return {"data": data, "count": len(data)}


async def import_snapshot_helper(
    pool,
    data: List[Dict[str, Any]],
) -> int:
    """Import orders from snapshot data."""
    import json
    imported = 0
    async with pool.acquire() as conn:
        for row in data:
            payload_json = json.dumps(row.get("payload") or {})
            try:
                await conn.execute("""
                    INSERT INTO orders (order_id, quantity, payload, created_at, updated_at)
                    VALUES ($1, $2, $3::jsonb, $4, $5)
                    ON CONFLICT (order_id) DO UPDATE SET
                        quantity = EXCLUDED.quantity,
                        payload = EXCLUDED.payload,
                        updated_at = EXCLUDED.updated_at
                """,
                    UUID(row["order_id"]) if isinstance(row["order_id"], str) else row["order_id"],
                    row["quantity"],
                    payload_json,
                    datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")) if row.get("created_at") else datetime.now(timezone.utc),
                    datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00")) if row.get("updated_at") else datetime.now(timezone.utc),
                )
                imported += 1
            except Exception as e:
                _LOGGER.warning("Failed to import row %s: %s", row.get("order_id"), e)
    return imported


# Global recovery flag for write gating
_RECOVERY_FLAG = False


def set_recovery_flag(flag: bool) -> None:
    """Set global recovery flag to gate writes."""
    global _RECOVERY_FLAG
    _RECOVERY_FLAG = flag


def get_recovery_flag() -> bool:
    """Get current recovery flag status."""
    return _RECOVERY_FLAG
