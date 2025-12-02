"""Recovery Subsystem - Core Recovery Manager.

This module implements the Recovery Subsystem for the distributed database demo.
It handles Leader Recovery (Node0) and Replica Promotion Recovery scenarios.

State Machine: STARTUP -> NEEDS_REBUILD -> SYNCING -> READY

Recovery Flow:
1. On startup, check last_applied_lamport
2. Fetch missing ops from peers using GET /oplog?since_lamport=X
3. Merge op_logs from peers, sort by (lamport, origin_node)
4. Replay ops with partition move handling
5. Resolve conflicts using Last-Writer-Wins (highest Lamport wins)
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from uuid import UUID, uuid4

import asyncpg

from ..config import PeerNode, Settings
from ..models import OpRecord
from ..utils.http_client import HTTPClient
from ..utils.partition import target_node_for_quantity

_LOGGER = logging.getLogger(__name__)


class RecoveryState(str, Enum):
    """State machine states for recovery process."""
    STARTUP = "startup"
    NEEDS_REBUILD = "needs_rebuild"
    SYNCING = "syncing"
    READY = "ready"
    FAILED = "failed"


class RecoveryMode(str, Enum):
    """Recovery mode selection."""
    LEADER = "leader"  # Node0 recovering as leader
    NODE = "node"  # Replica node recovery (promotion scenario)


@dataclass
class RecoveryProgress:
    """Tracks recovery progress metrics."""
    state: RecoveryState = RecoveryState.STARTUP
    mode: RecoveryMode = RecoveryMode.LEADER
    ops_fetched: int = 0
    ops_merged: int = 0
    ops_applied: int = 0
    ops_remaining: int = 0
    ops_skipped: int = 0
    ops_conflicted: int = 0
    peers_contacted: int = 0
    peers_failed: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    last_error: Optional[str] = None
    local_lamport_start: int = 0
    local_lamport_end: int = 0
    

@dataclass
class RecoveryJob:
    """Represents a single recovery job."""
    job_id: str
    mode: RecoveryMode
    progress: RecoveryProgress = field(default_factory=RecoveryProgress)
    logs: List[str] = field(default_factory=list)
    is_running: bool = False
    task: Optional[asyncio.Task] = None


class RecoveryManager:
    """Core recovery engine implementing the state machine.
    
    This manager handles:
    - Leader Recovery (Node0): Sync from replicas when leader comes back up
    - Promotion Recovery: Handle ops written to replicas during leader downtime
    
    State Machine Flow:
    STARTUP -> NEEDS_REBUILD (if behind) -> SYNCING -> READY
    """
    
    def __init__(
        self,
        pool: asyncpg.Pool,
        settings: Settings,
        http_client: Optional[HTTPClient] = None,
        applier_trigger: Optional[Callable] = None,
    ) -> None:
        self.pool = pool
        self.settings = settings
        self.http_client = http_client or HTTPClient()
        self.applier_trigger = applier_trigger
        
        # Recovery state
        self._state = RecoveryState.STARTUP
        self._jobs: Dict[str, RecoveryJob] = {}
        self._current_job_id: Optional[str] = None
        self._lock = asyncio.Lock()
        
        # Configuration
        self._sync_threshold = 5  # Gap threshold to consider "caught up"
        self._batch_size = 500  # Ops to fetch per peer per request
        self._max_retries = 3
        
    @property
    def state(self) -> RecoveryState:
        return self._state
    
    @property
    def is_ready(self) -> bool:
        return self._state == RecoveryState.READY
    
    @property
    def is_syncing(self) -> bool:
        return self._state == RecoveryState.SYNCING
    
    def get_job(self, job_id: str) -> Optional[RecoveryJob]:
        return self._jobs.get(job_id)
    
    def get_all_jobs(self) -> Dict[str, RecoveryJob]:
        return self._jobs.copy()
    
    async def start_recovery(self, mode: RecoveryMode) -> str:
        """Start a new recovery job.
        
        Args:
            mode: RecoveryMode.LEADER for leader recovery, RecoveryMode.NODE for replica
            
        Returns:
            job_id: Unique identifier for the recovery job
        """
        async with self._lock:
            # Check if recovery is already in progress
            if self._current_job_id and self._jobs[self._current_job_id].is_running:
                raise RuntimeError("Recovery already in progress")
            
            job_id = str(uuid4())[:8]
            job = RecoveryJob(
                job_id=job_id,
                mode=mode,
                progress=RecoveryProgress(
                    state=RecoveryState.STARTUP,
                    mode=mode,
                    start_time=datetime.now(timezone.utc),
                ),
            )
            self._jobs[job_id] = job
            self._current_job_id = job_id
            
            # Start the recovery task
            job.is_running = True
            job.task = asyncio.create_task(self._run_recovery(job_id))
            
            self._log(job_id, f"Recovery job started: mode={mode.value}")
            return job_id
    
    async def _run_recovery(self, job_id: str) -> None:
        """Main recovery execution flow."""
        job = self._jobs[job_id]
        try:
            # Step A: Check local state
            await self._step_a_check_local_state(job_id)
            
            # Step B: Determine if rebuild needed
            await self._step_b_check_rebuild_needed(job_id)
            
            if job.progress.state == RecoveryState.NEEDS_REBUILD:
                # Enter syncing mode
                await self._transition_state(job_id, RecoveryState.SYNCING)
                
                # Step C: Fetch and merge ops from peers
                merged_ops = await self._step_c_fetch_and_merge(job_id)
                
                # Step D: Apply ops with conflict resolution
                await self._step_d_apply_ops(job_id, merged_ops)
            
            # Step E: Finalize - enter READY state
            await self._step_e_finalize(job_id)
            
        except Exception as e:
            _LOGGER.exception("Recovery failed for job %s", job_id)
            job.progress.state = RecoveryState.FAILED
            job.progress.last_error = str(e)
            self._state = RecoveryState.FAILED
            self._log(job_id, f"ERROR: Recovery failed - {e}")
        finally:
            job.is_running = False
            job.progress.end_time = datetime.now(timezone.utc)
    
    async def _step_a_check_local_state(self, job_id: str) -> None:
        """Step A: Check last_applied_lamport to determine local state."""
        job = self._jobs[job_id]
        self._log(job_id, "Step A: Checking local state...")
        
        async with self.pool.acquire() as conn:
            # Get the maximum lamport value from local op_log
            max_lamport = await conn.fetchval(
                "SELECT COALESCE(MAX(lamport), 0) FROM op_log"
            )
            job.progress.local_lamport_start = int(max_lamport or 0)
            
            # Get count of unapplied ops
            unapplied = await conn.fetchval(
                "SELECT COUNT(*) FROM op_log WHERE applied = false"
            )
            job.progress.ops_remaining = int(unapplied or 0)
            
            self._log(
                job_id,
                f"Local state: max_lamport={job.progress.local_lamport_start}, "
                f"unapplied_ops={job.progress.ops_remaining}"
            )
    
    async def _step_b_check_rebuild_needed(self, job_id: str) -> None:
        """Step B: Check if rebuild is needed by comparing with peers."""
        job = self._jobs[job_id]
        self._log(job_id, "Step B: Checking if rebuild is needed...")
        
        local_max = job.progress.local_lamport_start
        peer_max = 0
        
        # Query each peer for their max lamport
        for peer in self.settings.peer_nodes:
            if peer.name == self.settings.node_name:
                continue
            try:
                # Fetch a single op to get max lamport
                payload = await self.http_client.get_json(
                    f"{peer.base_url}/oplog",
                    params={"since_lamport": local_max, "limit": 1},
                )
                if payload:
                    op_lamport = payload[0].get("lamport", 0)
                    peer_max = max(peer_max, op_lamport)
                job.progress.peers_contacted += 1
                self._log(job_id, f"Contacted peer {peer.name}: has newer ops")
            except Exception as e:
                job.progress.peers_failed += 1
                self._log(job_id, f"WARNING: Failed to contact peer {peer.name}: {e}")
        
        # Determine if rebuild needed
        gap = peer_max - local_max if peer_max > local_max else 0
        
        if gap > 0 or job.progress.ops_remaining > 0:
            await self._transition_state(job_id, RecoveryState.NEEDS_REBUILD)
            self._log(
                job_id,
                f"Rebuild needed: local_max={local_max}, peer_max={peer_max}, gap={gap}"
            )
        else:
            self._log(job_id, "No rebuild needed - already caught up")
    
    async def _step_c_fetch_and_merge(self, job_id: str) -> List[OpRecord]:
        """Step C: Fetch missing ops from peers and merge them."""
        job = self._jobs[job_id]
        self._log(job_id, "Step C: Fetching and merging ops from peers...")
        
        since_lamport = job.progress.local_lamport_start
        all_ops: Dict[UUID, OpRecord] = {}  # Dedupe by op_id
        
        for peer in self.settings.peer_nodes:
            if peer.name == self.settings.node_name:
                continue
            
            try:
                self._log(job_id, f"Fetching ops from {peer.name} since lamport={since_lamport}...")
                
                # Paginated fetch from peer
                peer_ops = await self._fetch_ops_from_peer(peer, since_lamport)
                job.progress.ops_fetched += len(peer_ops)
                
                # Dedupe and merge
                for op in peer_ops:
                    if op.op_id not in all_ops:
                        all_ops[op.op_id] = op
                    else:
                        # Conflict resolution: Last-Writer-Wins (highest Lamport)
                        existing = all_ops[op.op_id]
                        if op.lamport > existing.lamport:
                            all_ops[op.op_id] = op
                            job.progress.ops_conflicted += 1
                        elif op.lamport == existing.lamport:
                            # Tie-breaker: origin_node (lexicographic)
                            if op.origin_node > existing.origin_node:
                                all_ops[op.op_id] = op
                                job.progress.ops_conflicted += 1
                
                self._log(job_id, f"Fetched {len(peer_ops)} ops from {peer.name}")
                
            except Exception as e:
                job.progress.peers_failed += 1
                self._log(job_id, f"WARNING: Failed to fetch from {peer.name}: {e}")
        
        # Sort merged ops by (lamport, origin_node) for deterministic replay
        merged_ops = sorted(
            all_ops.values(),
            key=lambda op: (op.lamport, op.origin_node)
        )
        job.progress.ops_merged = len(merged_ops)
        self._log(
            job_id,
            f"Merged {len(merged_ops)} unique ops (conflicts resolved: {job.progress.ops_conflicted})"
        )
        
        return merged_ops
    
    async def _fetch_ops_from_peer(
        self,
        peer: PeerNode,
        since_lamport: int
    ) -> List[OpRecord]:
        """Fetch all ops from a peer since the given lamport value."""
        all_ops: List[OpRecord] = []
        current_lamport = since_lamport
        
        for _ in range(100):  # Safety limit to prevent infinite loops
            payload = await self.http_client.get_json(
                f"{peer.base_url}/oplog",
                params={
                    "since_lamport": current_lamport,
                    "limit": self._batch_size,
                },
            )
            
            if not payload:
                break
            
            ops = [OpRecord(**item) for item in payload]
            all_ops.extend(ops)
            
            # Update cursor for next batch
            max_lamport = max(op.lamport for op in ops)
            if max_lamport == current_lamport:
                break
            current_lamport = max_lamport
            
            # If we got fewer than batch size, we're done
            if len(ops) < self._batch_size:
                break
        
        return all_ops
    
    async def _step_d_apply_ops(self, job_id: str, ops: List[OpRecord]) -> None:
        """Step D: Apply ops with partition move handling and conflict resolution."""
        job = self._jobs[job_id]
        self._log(job_id, f"Step D: Applying {len(ops)} ops...")
        
        job.progress.ops_remaining = len(ops)
        
        async with self.pool.acquire() as conn:
            for op in ops:
                try:
                    await self._apply_single_op(conn, op, job_id)
                    job.progress.ops_applied += 1
                    job.progress.ops_remaining -= 1
                    
                    # Log progress every 100 ops
                    if job.progress.ops_applied % 100 == 0:
                        self._log(
                            job_id,
                            f"Progress: {job.progress.ops_applied}/{len(ops)} ops applied"
                        )
                        
                except Exception as e:
                    _LOGGER.warning("Failed to apply op %s: %s", op.op_id, e)
                    job.progress.ops_skipped += 1
                    self._log(job_id, f"WARNING: Skipped op {op.op_id}: {e}")
        
        self._log(
            job_id,
            f"Applied {job.progress.ops_applied} ops, skipped {job.progress.ops_skipped}"
        )
    
    async def _apply_single_op(
        self,
        conn: asyncpg.Connection,
        op: OpRecord,
        job_id: str
    ) -> None:
        """Apply a single operation with partition move handling.
        
        Handles:
        - Inserts/Updates (upsert operations)
        - Deletes
        - Partition moves (when quantity changes partition boundary)
        - Last-Writer-Wins conflict resolution
        """
        job = self._jobs[job_id]
        
        async with conn.transaction():
            # First, insert the op into local op_log if missing
            await self._insert_op_if_missing(conn, op)
            
            if op.op_type == "delete":
                # Handle delete operation
                await conn.execute(
                    "DELETE FROM orders WHERE order_id = $1",
                    op.row_id
                )
            else:
                # Handle upsert operation with partition awareness
                payload = op.payload or {}
                quantity = payload.get("quantity")
                order_payload = payload.get("payload")
                
                # Check for partition move (if applicable on replicas)
                if self.settings.node_name != self.settings.default_master:
                    target_node = target_node_for_quantity(
                        quantity,
                        self.settings.partition_rule
                    )
                    
                    if target_node != self.settings.node_name.lower():
                        # This op belongs to a different partition
                        # Delete local copy if exists (partition move out)
                        await conn.execute(
                            "DELETE FROM orders WHERE order_id = $1",
                            op.row_id
                        )
                        job.progress.ops_skipped += 1
                        return
                
                # Check for conflict - Last-Writer-Wins
                existing = await conn.fetchrow(
                    """
                    SELECT lamport FROM op_log 
                    WHERE row_id = $1 AND lamport > $2
                    ORDER BY lamport DESC, origin_node DESC
                    LIMIT 1
                    """,
                    op.row_id,
                    op.lamport
                )
                
                if existing:
                    # A newer op exists - skip this one
                    job.progress.ops_conflicted += 1
                    return
                
                # Apply the upsert
                order_payload_json = json.dumps(order_payload) if order_payload else None
                await conn.execute(
                    """
                    INSERT INTO orders (order_id, quantity, payload, created_at, updated_at)
                    VALUES ($1, $2, $3::jsonb, $4, $4)
                    ON CONFLICT (order_id)
                    DO UPDATE SET 
                        quantity = EXCLUDED.quantity,
                        payload = EXCLUDED.payload,
                        updated_at = EXCLUDED.updated_at
                    """,
                    op.row_id,
                    quantity,
                    order_payload_json,
                    op.ts,
                )
            
            # Mark as applied
            await conn.execute(
                """
                UPDATE op_log SET applied = true, applied_ts = $2
                WHERE op_id = $1
                """,
                op.op_id,
                datetime.now(timezone.utc),
            )
    
    async def _insert_op_if_missing(
        self,
        conn: asyncpg.Connection,
        op: OpRecord
    ) -> bool:
        """Insert an op into local op_log if not already present."""
        payload_json = json.dumps(op.payload or {})
        result = await conn.execute(
            """
            INSERT INTO op_log (
                op_id, origin_node, op_type, table_name, row_id, payload,
                ts, lamport, applied, applied_ts
            ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, false, NULL)
            ON CONFLICT (op_id) DO NOTHING
            """,
            op.op_id,
            op.origin_node,
            op.op_type,
            op.table_name,
            op.row_id,
            payload_json,
            op.ts,
            op.lamport,
        )
        return result.endswith("INSERT 0 1")
    
    async def _step_e_finalize(self, job_id: str) -> None:
        """Step E: Finalize recovery and transition to READY state."""
        job = self._jobs[job_id]
        self._log(job_id, "Step E: Finalizing recovery...")
        
        async with self.pool.acquire() as conn:
            # Get final lamport value
            max_lamport = await conn.fetchval(
                "SELECT COALESCE(MAX(lamport), 0) FROM op_log"
            )
            job.progress.local_lamport_end = int(max_lamport or 0)
            
            # Update replication cursors for all peers
            for peer in self.settings.peer_nodes:
                if peer.name != self.settings.node_name:
                    await conn.execute(
                        """
                        INSERT INTO replication_cursors (node, last_lamport)
                        VALUES ($1, $2)
                        ON CONFLICT (node) DO UPDATE SET last_lamport = EXCLUDED.last_lamport
                        """,
                        peer.name,
                        job.progress.local_lamport_end,
                    )
        
        # Trigger the applier if available
        if self.applier_trigger:
            try:
                await self.applier_trigger()
                self._log(job_id, "Triggered applier for remaining ops")
            except Exception as e:
                self._log(job_id, f"WARNING: Failed to trigger applier: {e}")
        
        # Transition to READY
        await self._transition_state(job_id, RecoveryState.READY)
        self._log(
            job_id,
            f"Recovery complete! Lamport: {job.progress.local_lamport_start} -> "
            f"{job.progress.local_lamport_end}, Ops applied: {job.progress.ops_applied}"
        )
    
    async def _transition_state(self, job_id: str, new_state: RecoveryState) -> None:
        """Transition the recovery state machine."""
        job = self._jobs[job_id]
        old_state = job.progress.state
        job.progress.state = new_state
        self._state = new_state
        self._log(job_id, f"State transition: {old_state.value} -> {new_state.value}")
    
    def _log(self, job_id: str, message: str) -> None:
        """Add a log entry to the job."""
        timestamp = datetime.now(timezone.utc).isoformat()
        log_entry = f"[{timestamp}] {message}"
        
        if job_id in self._jobs:
            self._jobs[job_id].logs.append(log_entry)
        
        _LOGGER.info("[Recovery:%s] %s", job_id, message)
    
    # --- Health Check Methods ---
    
    async def get_node_health(self) -> Dict[str, Any]:
        """Get health status of this node and peers."""
        health = {
            "node": self.settings.node_name,
            "state": self._state.value,
            "is_ready": self.is_ready,
            "local_stats": await self._get_local_stats(),
            "peers": [],
        }
        
        # Check peer health
        for peer in self.settings.peer_nodes:
            if peer.name == self.settings.node_name:
                continue
            peer_status = await self._check_peer_health(peer)
            health["peers"].append(peer_status)
        
        return health
    
    async def _get_local_stats(self) -> Dict[str, Any]:
        """Get local database statistics."""
        async with self.pool.acquire() as conn:
            max_lamport = await conn.fetchval(
                "SELECT COALESCE(MAX(lamport), 0) FROM op_log"
            )
            total_ops = await conn.fetchval("SELECT COUNT(*) FROM op_log")
            unapplied_ops = await conn.fetchval(
                "SELECT COUNT(*) FROM op_log WHERE applied = false"
            )
            total_orders = await conn.fetchval("SELECT COUNT(*) FROM orders")
        
        return {
            "max_lamport": int(max_lamport or 0),
            "total_ops": int(total_ops or 0),
            "unapplied_ops": int(unapplied_ops or 0),
            "total_orders": int(total_orders or 0),
        }
    
    async def _check_peer_health(self, peer: PeerNode) -> Dict[str, Any]:
        """Check health status of a peer node."""
        try:
            response = await self.http_client.get_json(f"{peer.base_url}/")
            return {
                "name": peer.name,
                "url": peer.base_url,
                "status": "healthy",
                "promoted": response.get("promoted", False),
            }
        except Exception as e:
            return {
                "name": peer.name,
                "url": peer.base_url,
                "status": "unreachable",
                "error": str(e),
            }
    
    # --- Snapshot Methods ---
    
    async def force_snapshot(self) -> Dict[str, Any]:
        """Force a snapshot by syncing all ops from peers.
        
        This is a manual trigger for full resync.
        """
        job_id = await self.start_recovery(RecoveryMode.LEADER)
        return {
            "job_id": job_id,
            "message": "Snapshot/resync initiated",
        }
    
    async def get_sync_gap(self) -> Dict[str, int]:
        """Calculate the sync gap between this node and peers."""
        async with self.pool.acquire() as conn:
            local_max = await conn.fetchval(
                "SELECT COALESCE(MAX(lamport), 0) FROM op_log"
            )
        local_max = int(local_max or 0)
        
        gaps = {"local_max_lamport": local_max}
        
        for peer in self.settings.peer_nodes:
            if peer.name == self.settings.node_name:
                continue
            try:
                payload = await self.http_client.get_json(
                    f"{peer.base_url}/oplog",
                    params={"since_lamport": local_max, "limit": 1},
                )
                if payload:
                    peer_lamport = payload[0].get("lamport", local_max)
                    gaps[f"gap_{peer.name}"] = peer_lamport - local_max
                else:
                    gaps[f"gap_{peer.name}"] = 0
            except Exception:
                gaps[f"gap_{peer.name}"] = -1  # Indicates error
        
        return gaps
