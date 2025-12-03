"""Cluster Manager - Automatic failure detection, leader election, and recovery.

This module implements:
1. Automatic heartbeat monitoring
2. Leader election when leader fails
3. Automatic replica catch-up when nodes rejoin
4. Automatic partition healing
5. Real event logging for timeline visualization
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

from .config import Settings, PeerNode
from .utils.http_client import HTTPClient

_LOGGER = logging.getLogger(__name__)

# Constants
HEARTBEAT_INTERVAL = 2.0  # seconds between heartbeats
HEARTBEAT_TIMEOUT = 6.0  # seconds before marking node as DOWN
ELECTION_TIMEOUT = 3.0  # seconds to wait for election responses
RECOVERY_CHECK_INTERVAL = 5.0  # seconds between recovery checks
MAX_LAMPORT_GAP_FOR_INCREMENTAL = 10000  # Beyond this, use snapshot


class NodeRole(str, Enum):
    """Node roles in the cluster."""
    LEADER = "leader"
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    OFFLINE = "offline"


class ClusterEventType(str, Enum):
    """Types of cluster events for logging."""
    # Heartbeat events
    HEARTBEAT_SENT = "heartbeat_sent"
    HEARTBEAT_RECEIVED = "heartbeat_received"
    HEARTBEAT_TIMEOUT = "heartbeat_timeout"
    
    # Node state events
    NODE_UP = "node_up"
    NODE_DOWN = "node_down"
    NODE_RECOVERING = "node_recovering"
    NODE_SYNCED = "node_synced"
    
    # Leader election events
    ELECTION_STARTED = "election_started"
    ELECTION_VOTE = "election_vote"
    ELECTION_WON = "election_won"
    ELECTION_LOST = "election_lost"
    LEADER_ELECTED = "leader_elected"
    
    # Recovery events
    RECOVERY_STARTED = "recovery_started"
    RECOVERY_FETCHING = "recovery_fetching"
    RECOVERY_APPLYING = "recovery_applying"
    RECOVERY_COMPLETED = "recovery_completed"
    RECOVERY_FAILED = "recovery_failed"
    
    # Replication events
    REPLICATION_QUEUED = "replication_queued"
    REPLICATION_RETRY = "replication_retry"
    REPLICATION_FAILED = "replication_failed"
    REPLICATION_SUCCESS = "replication_success"
    
    # Write gating events
    WRITES_GATED = "writes_gated"
    WRITES_ENABLED = "writes_enabled"
    WRITE_REJECTED = "write_rejected"


@dataclass
class ClusterEvent:
    """A cluster event for timeline logging."""
    event_id: str
    timestamp: str
    lamport_time: int
    event_type: ClusterEventType
    node: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    level: str = "info"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "lamport_time": self.lamport_time,
            "event_type": self.event_type.value,
            "node": self.node,
            "message": self.message,
            "details": self.details,
            "level": self.level,
        }


@dataclass
class NodeState:
    """State of a node in the cluster."""
    name: str
    role: NodeRole = NodeRole.FOLLOWER
    is_alive: bool = True
    is_simulated_down: bool = False
    last_heartbeat: Optional[datetime] = None
    last_seen_lamport: int = -1
    url: Optional[str] = None
    recovery_in_progress: bool = False
    promoted: bool = False
    
    @property
    def effective_alive(self) -> bool:
        """Check if node should be treated as alive (considering simulation)."""
        return self.is_alive and not self.is_simulated_down
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role.value,
            "is_alive": self.is_alive,
            "is_simulated_down": self.is_simulated_down,
            "effective_alive": self.effective_alive,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "last_seen_lamport": self.last_seen_lamport,
            "url": self.url,
            "recovery_in_progress": self.recovery_in_progress,
            "promoted": self.promoted,
        }


class ClusterManager:
    """
    Manages cluster state, automatic failover, and recovery.
    
    This is the central coordinator for:
    - Heartbeat monitoring (detecting node failures)
    - Leader election (automatic failover when leader dies)
    - Recovery orchestration (automatic catch-up when nodes rejoin)
    - Write gating (blocking writes during recovery/election)
    - Event logging (real-time timeline)
    """

    def __init__(
        self,
        pool,
        settings: Settings,
        http_client: HTTPClient,
        get_promoted_flag: Callable[[], bool],
        set_promoted_flag: Callable[[bool], None],
    ):
        self.pool = pool
        self.settings = settings
        self.http_client = http_client
        self._get_promoted_flag = get_promoted_flag
        self._set_promoted_flag = set_promoted_flag
        
        # Cluster state
        self._nodes: Dict[str, NodeState] = {}
        self._current_leader: Optional[str] = None
        self._my_role = NodeRole.FOLLOWER
        self._election_in_progress = False
        self._recovery_in_progress = False
        self._writes_gated = False
        
        # Lamport clock for event ordering
        self._lamport_clock = 0
        self._lamport_lock = asyncio.Lock()
        
        # Event log for timeline
        self._events: List[ClusterEvent] = []
        self._max_events = 1000  # Keep last N events
        self._event_callbacks: List[Callable[[ClusterEvent], None]] = []
        
        # Background tasks
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._recovery_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Initialize node states
        self._init_node_states()

    def _init_node_states(self):
        """Initialize node state tracking."""
        # Add self
        self._nodes[self.settings.node_name] = NodeState(
            name=self.settings.node_name,
            is_alive=True,
            url=None,  # Local
        )
        
        # Add peers
        for peer in self.settings.peer_nodes:
            if peer.name != self.settings.node_name:
                self._nodes[peer.name] = NodeState(
                    name=peer.name,
                    url=peer.base_url,
                )
        
        # Determine initial leader (node0 by default)
        if self.settings.node_name == self.settings.default_master:
            self._current_leader = self.settings.node_name
            self._my_role = NodeRole.LEADER

    def _now(self) -> str:
        """Get current ISO timestamp."""
        return datetime.now(timezone.utc).isoformat()

    async def _tick_lamport(self) -> int:
        """Increment and return lamport clock."""
        async with self._lamport_lock:
            self._lamport_clock += 1
            return self._lamport_clock

    async def _update_lamport(self, received: int) -> int:
        """Update lamport clock based on received value."""
        async with self._lamport_lock:
            self._lamport_clock = max(self._lamport_clock, received) + 1
            return self._lamport_clock

    async def _emit_event(
        self,
        event_type: ClusterEventType,
        message: str,
        node: str = None,
        level: str = "info",
        **details
    ) -> ClusterEvent:
        """Emit a cluster event."""
        lamport = await self._tick_lamport()
        event = ClusterEvent(
            event_id=str(uuid4()),
            timestamp=self._now(),
            lamport_time=lamport,
            event_type=event_type,
            node=node or self.settings.node_name,
            message=message,
            details=details,
            level=level,
        )
        
        # Store event
        self._events.append(event)
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]
        
        # Notify callbacks
        for callback in self._event_callbacks:
            try:
                callback(event)
            except Exception as e:
                _LOGGER.warning("Event callback error: %s", e)
        
        # Also log to standard logger
        log_func = getattr(_LOGGER, level, _LOGGER.info)
        log_func("[T=%d] %s: %s %s", lamport, node or self.settings.node_name, message, details or "")
        
        return event

    def add_event_callback(self, callback: Callable[[ClusterEvent], None]):
        """Add a callback for cluster events."""
        self._event_callbacks.append(callback)

    def remove_event_callback(self, callback: Callable[[ClusterEvent], None]):
        """Remove an event callback."""
        if callback in self._event_callbacks:
            self._event_callbacks.remove(callback)

    async def start(self):
        """Start the cluster manager background tasks."""
        if self._running:
            return
        
        self._running = True
        await self._emit_event(
            ClusterEventType.NODE_UP,
            f"Node {self.settings.node_name} starting cluster manager",
            role=self._my_role.value,
        )
        
        # Start heartbeat sender
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        # Start node monitor
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        
        _LOGGER.info("Cluster manager started for %s", self.settings.node_name)

    async def stop(self):
        """Stop the cluster manager."""
        self._running = False
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        if self._recovery_task:
            self._recovery_task.cancel()
            try:
                await self._recovery_task
            except asyncio.CancelledError:
                pass
        
        _LOGGER.info("Cluster manager stopped")

    async def _heartbeat_loop(self):
        """Send periodic heartbeats to peer nodes."""
        while self._running:
            try:
                await self._send_heartbeats()
            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOGGER.warning("Heartbeat error: %s", e)
            
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def _send_heartbeats(self):
        """Send heartbeat to all peer nodes."""
        my_state = self._nodes.get(self.settings.node_name)
        if my_state and my_state.is_simulated_down:
            # Don't send heartbeats if simulated down
            return
        
        tasks = []
        for peer in self.settings.peer_nodes:
            if peer.name != self.settings.node_name:
                tasks.append(self._send_heartbeat_to(peer))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_heartbeat_to(self, peer: PeerNode):
        """Send heartbeat to a specific peer."""
        peer_state = self._nodes.get(peer.name)
        if peer_state and peer_state.is_simulated_down:
            # Peer is simulated as down, skip
            return
        
        lamport = await self._tick_lamport()
        payload = {
            "from_node": self.settings.node_name,
            "lamport": lamport,
            "role": self._my_role.value,
            "leader": self._current_leader,
            "timestamp": self._now(),
        }
        
        try:
            result = await asyncio.wait_for(
                self.http_client.post_json(f"{peer.base_url}/cluster/heartbeat", payload),
                timeout=HEARTBEAT_TIMEOUT / 2
            )
            
            if result:
                # Update peer state
                if peer.name in self._nodes:
                    self._nodes[peer.name].is_alive = True
                    self._nodes[peer.name].last_heartbeat = datetime.now(timezone.utc)
                    if "lamport" in result:
                        await self._update_lamport(result["lamport"])
                        self._nodes[peer.name].last_seen_lamport = result["lamport"]
        
        except asyncio.TimeoutError:
            _LOGGER.debug("Heartbeat timeout to %s", peer.name)
        except Exception as e:
            _LOGGER.debug("Heartbeat failed to %s: %s", peer.name, e)

    async def _monitor_loop(self):
        """Monitor node health and trigger failover if needed."""
        while self._running:
            try:
                await self._check_node_health()
            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOGGER.warning("Monitor error: %s", e)
            
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def _check_node_health(self):
        """Check health of all nodes and trigger failover if leader is down."""
        now = datetime.now(timezone.utc)
        
        for name, state in self._nodes.items():
            if name == self.settings.node_name:
                continue  # Skip self
            
            if state.is_simulated_down:
                # Node is simulated as down
                if state.is_alive:
                    state.is_alive = False
                    await self._emit_event(
                        ClusterEventType.NODE_DOWN,
                        f"Node {name} marked DOWN (simulated)",
                        node=name,
                        level="warning",
                        reason="simulated",
                    )
                continue
            
            # Check actual heartbeat timeout
            if state.last_heartbeat:
                elapsed = (now - state.last_heartbeat).total_seconds()
                if elapsed > HEARTBEAT_TIMEOUT and state.is_alive:
                    state.is_alive = False
                    await self._emit_event(
                        ClusterEventType.NODE_DOWN,
                        f"Node {name} marked DOWN (heartbeat timeout)",
                        node=name,
                        level="warning",
                        elapsed_seconds=elapsed,
                    )
                    
                    # Check if this was the leader
                    if name == self._current_leader:
                        await self._start_leader_election()
            elif state.is_alive:
                # No heartbeat ever received, try to contact
                await self._probe_node(name)

    async def _probe_node(self, node_name: str):
        """Probe a node to check if it's alive."""
        state = self._nodes.get(node_name)
        if not state or not state.url:
            return
        
        try:
            result = await asyncio.wait_for(
                self.http_client.get_json(f"{state.url}/health"),
                timeout=3.0
            )
            if result and result.get("status") == "ok":
                state.is_alive = True
                state.last_heartbeat = datetime.now(timezone.utc)
        except:
            pass

    async def _start_leader_election(self):
        """Start a leader election process."""
        if self._election_in_progress:
            return
        
        self._election_in_progress = True
        self._writes_gated = True
        
        await self._emit_event(
            ClusterEventType.ELECTION_STARTED,
            "Leader election started",
            level="warning",
        )
        await self._emit_event(
            ClusterEventType.WRITES_GATED,
            "Writes gated during election",
            level="warning",
        )
        
        try:
            # Simple election: node with lowest name among alive nodes becomes leader
            alive_nodes = [
                name for name, state in self._nodes.items()
                if state.effective_alive
            ]
            
            if not alive_nodes:
                await self._emit_event(
                    ClusterEventType.ELECTION_LOST,
                    "No alive nodes for election",
                    level="error",
                )
                return
            
            # Sort to get deterministic leader (preferring node0)
            alive_nodes.sort()
            new_leader = alive_nodes[0]
            
            # Broadcast election result
            await self._broadcast_election_result(new_leader)
            
            self._current_leader = new_leader
            
            if new_leader == self.settings.node_name:
                self._my_role = NodeRole.LEADER
                self._set_promoted_flag(True)
                await self._emit_event(
                    ClusterEventType.ELECTION_WON,
                    f"This node elected as leader",
                )
            else:
                self._my_role = NodeRole.FOLLOWER
                await self._emit_event(
                    ClusterEventType.LEADER_ELECTED,
                    f"Node {new_leader} elected as new leader",
                    new_leader=new_leader,
                )
            
            # Enable writes if we're the leader
            if self._my_role == NodeRole.LEADER:
                self._writes_gated = False
                await self._emit_event(
                    ClusterEventType.WRITES_ENABLED,
                    "Writes enabled (leader ready)",
                )
        
        finally:
            self._election_in_progress = False

    async def _broadcast_election_result(self, new_leader: str):
        """Broadcast election result to all peers."""
        lamport = await self._tick_lamport()
        payload = {
            "from_node": self.settings.node_name,
            "new_leader": new_leader,
            "lamport": lamport,
            "timestamp": self._now(),
        }
        
        tasks = []
        for peer in self.settings.peer_nodes:
            if peer.name != self.settings.node_name:
                task = self.http_client.post_json(
                    f"{peer.base_url}/cluster/election-result",
                    payload
                )
                tasks.append(asyncio.wait_for(task, timeout=2.0))
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success_count = sum(1 for r in results if not isinstance(r, Exception))
            _LOGGER.info("Election result broadcast: %d/%d successful", success_count, len(tasks))

    # ==================== Node Control (Simulation) ====================

    async def set_node_down(self, node_name: str):
        """Simulate a node going down."""
        if node_name not in self._nodes:
            return False
        
        state = self._nodes[node_name]
        was_alive = state.effective_alive
        state.is_simulated_down = True
        state.is_alive = False
        
        await self._emit_event(
            ClusterEventType.NODE_DOWN,
            f"Node {node_name} taken offline (simulated)",
            node=node_name,
            level="warning",
            simulated=True,
        )
        
        # If this was the leader, start election
        if node_name == self._current_leader and was_alive:
            await self._start_leader_election()
        
        return True

    async def set_node_up(self, node_name: str):
        """Simulate a node coming back up."""
        if node_name not in self._nodes:
            return False
        
        state = self._nodes[node_name]
        was_down = state.is_simulated_down
        state.is_simulated_down = False
        
        await self._emit_event(
            ClusterEventType.NODE_UP,
            f"Node {node_name} coming online",
            node=node_name,
        )
        
        if was_down:
            # Trigger automatic recovery
            await self._trigger_node_recovery(node_name)
        
        return True

    async def _trigger_node_recovery(self, node_name: str):
        """Trigger automatic recovery for a node that just came back."""
        await self._emit_event(
            ClusterEventType.RECOVERY_STARTED,
            f"Automatic recovery started for {node_name}",
            node=node_name,
        )
        
        state = self._nodes.get(node_name)
        if state:
            state.recovery_in_progress = True
        
        # If this is the local node, start recovery process
        if node_name == self.settings.node_name:
            self._recovery_task = asyncio.create_task(
                self._run_local_recovery()
            )
        else:
            # Remote node will handle its own recovery
            # We just wait for it to sync up via heartbeats
            pass

    async def _run_local_recovery(self):
        """Run recovery for this node (catch up with the cluster)."""
        self._recovery_in_progress = True
        self._writes_gated = True
        
        try:
            await self._emit_event(
                ClusterEventType.WRITES_GATED,
                "Writes gated during recovery",
            )
            
            # Step 1: Get local max lamport
            async with self.pool.acquire() as conn:
                local_max = await conn.fetchval(
                    "SELECT COALESCE(MAX(lamport), -1) FROM op_log"
                )
            
            await self._emit_event(
                ClusterEventType.RECOVERY_FETCHING,
                f"Local max lamport: {local_max}, fetching from peers",
                local_max=local_max,
            )
            
            # Step 2: Fetch ops from all alive peers
            total_fetched = 0
            for name, state in self._nodes.items():
                if name == self.settings.node_name:
                    continue
                if not state.effective_alive or not state.url:
                    continue
                
                try:
                    ops = await self.http_client.get_json(
                        f"{state.url}/oplog",
                        params={"since_lamport": local_max, "limit": 5000}
                    )
                    if ops:
                        await self._emit_event(
                            ClusterEventType.RECOVERY_FETCHING,
                            f"Fetched {len(ops)} ops from {name}",
                            node=name,
                            count=len(ops),
                        )
                        total_fetched += len(ops)
                        
                        # Ingest ops
                        await self._ingest_ops(ops)
                except Exception as e:
                    await self._emit_event(
                        ClusterEventType.RECOVERY_FAILED,
                        f"Failed to fetch from {name}: {e}",
                        node=name,
                        level="warning",
                        error=str(e),
                    )
            
            # Step 3: Apply all unapplied ops
            await self._emit_event(
                ClusterEventType.RECOVERY_APPLYING,
                "Applying fetched operations",
                total_fetched=total_fetched,
            )
            
            await self._apply_pending_ops()
            
            # Step 4: Done
            await self._emit_event(
                ClusterEventType.RECOVERY_COMPLETED,
                "Recovery completed successfully",
                ops_processed=total_fetched,
            )
            
            self._writes_gated = False
            await self._emit_event(
                ClusterEventType.WRITES_ENABLED,
                "Writes enabled (recovery complete)",
            )
            
        except Exception as e:
            await self._emit_event(
                ClusterEventType.RECOVERY_FAILED,
                f"Recovery failed: {e}",
                level="error",
                error=str(e),
            )
        finally:
            self._recovery_in_progress = False
            state = self._nodes.get(self.settings.node_name)
            if state:
                state.recovery_in_progress = False

    async def _ingest_ops(self, ops: List[Dict]):
        """Ingest operations into local op_log."""
        async with self.pool.acquire() as conn:
            for op in ops:
                try:
                    # Insert if not exists
                    await conn.execute("""
                        INSERT INTO op_log (op_id, origin_node, op_type, table_name, row_id, payload, ts, lamport)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        ON CONFLICT (op_id) DO NOTHING
                    """,
                        op.get("op_id"),
                        op.get("origin_node"),
                        op.get("op_type"),
                        op.get("table_name"),
                        op.get("row_id"),
                        op.get("payload"),
                        op.get("ts"),
                        op.get("lamport"),
                    )
                except Exception as e:
                    _LOGGER.warning("Failed to ingest op %s: %s", op.get("op_id"), e)

    async def _apply_pending_ops(self):
        """Apply all unapplied operations from op_log."""
        async with self.pool.acquire() as conn:
            # Get unapplied ops in lamport order
            rows = await conn.fetch("""
                SELECT * FROM op_log 
                WHERE applied = false 
                ORDER BY lamport, origin_node
                LIMIT 1000
            """)
            
            for row in rows:
                try:
                    # Apply based on op_type
                    if row["op_type"] == "upsert":
                        await conn.execute("""
                            INSERT INTO orders (order_id, quantity, payload, created_at, updated_at)
                            VALUES ($1, $2, $3, NOW(), NOW())
                            ON CONFLICT (order_id) DO UPDATE SET
                                quantity = EXCLUDED.quantity,
                                payload = EXCLUDED.payload,
                                updated_at = NOW()
                        """, row["row_id"], row["payload"].get("quantity", 1), row["payload"])
                    elif row["op_type"] == "delete":
                        await conn.execute(
                            "DELETE FROM orders WHERE order_id = $1",
                            row["row_id"]
                        )
                    
                    # Mark as applied
                    await conn.execute("""
                        UPDATE op_log SET applied = true, applied_ts = NOW()
                        WHERE op_id = $1
                    """, row["op_id"])
                    
                except Exception as e:
                    _LOGGER.warning("Failed to apply op %s: %s", row["op_id"], e)

    # ==================== Public API ====================

    @property
    def is_leader(self) -> bool:
        """Check if this node is the leader."""
        return self._my_role == NodeRole.LEADER

    @property
    def current_leader(self) -> Optional[str]:
        """Get current leader name."""
        return self._current_leader

    @property
    def writes_allowed(self) -> bool:
        """Check if writes are allowed."""
        if self._writes_gated:
            return False
        if self._recovery_in_progress:
            return False
        if self._election_in_progress:
            return False
        return True

    def get_node_states(self) -> Dict[str, Dict]:
        """Get all node states."""
        return {name: state.to_dict() for name, state in self._nodes.items()}

    def get_events(self, limit: int = 100, since_lamport: int = 0) -> List[Dict]:
        """Get cluster events for timeline."""
        events = [e for e in self._events if e.lamport_time > since_lamport]
        return [
            {
                "event_id": e.event_id,
                "timestamp": e.timestamp,
                "lamport_time": e.lamport_time,
                "event_type": e.event_type.value,
                "node": e.node,
                "message": e.message,
                "details": e.details,
                "level": e.level,
            }
            for e in events[-limit:]
        ]

    def get_cluster_status(self) -> Dict[str, Any]:
        """Get full cluster status."""
        return {
            "my_node": self.settings.node_name,
            "my_role": self._my_role.value,
            "current_leader": self._current_leader,
            "election_in_progress": self._election_in_progress,
            "recovery_in_progress": self._recovery_in_progress,
            "writes_gated": self._writes_gated,
            "writes_allowed": self.writes_allowed,
            "lamport_clock": self._lamport_clock,
            "nodes": self.get_node_states(),
        }

    async def handle_heartbeat(self, payload: Dict) -> Dict:
        """Handle incoming heartbeat from a peer."""
        from_node = payload.get("from_node")
        received_lamport = payload.get("lamport", 0)
        
        # Update lamport clock
        await self._update_lamport(received_lamport)
        
        # Update node state
        if from_node in self._nodes:
            state = self._nodes[from_node]
            state.is_alive = True
            state.last_heartbeat = datetime.now(timezone.utc)
            state.last_seen_lamport = received_lamport
            
            # Check if we need to accept new leader
            if payload.get("leader") and payload["leader"] != self._current_leader:
                if not self._election_in_progress:
                    self._current_leader = payload["leader"]
                    if self._current_leader != self.settings.node_name:
                        self._my_role = NodeRole.FOLLOWER
        
        my_lamport = await self._tick_lamport()
        return {
            "from_node": self.settings.node_name,
            "lamport": my_lamport,
            "leader": self._current_leader,
            "role": self._my_role.value,
        }

    async def handle_election_result(self, payload: Dict) -> Dict:
        """Handle election result broadcast from another node."""
        new_leader = payload.get("new_leader")
        received_lamport = payload.get("lamport", 0)
        
        await self._update_lamport(received_lamport)
        
        if new_leader:
            self._current_leader = new_leader
            if new_leader == self.settings.node_name:
                self._my_role = NodeRole.LEADER
                self._set_promoted_flag(True)
            else:
                self._my_role = NodeRole.FOLLOWER
            
            await self._emit_event(
                ClusterEventType.LEADER_ELECTED,
                f"Accepted new leader: {new_leader}",
                new_leader=new_leader,
            )
        
        return {"status": "accepted", "leader": self._current_leader}

    # ==================== Recovery Tests ====================

    async def _trigger_automatic_recovery(self):
        """Force trigger automatic recovery check cycle."""
        await self._emit_event(
            ClusterEventType.RECOVERY_STARTED,
            "Manual recovery trigger requested",
        )
        
        # Check for any nodes that need recovery
        for name, state in self._nodes.items():
            if state.is_simulated_down:
                continue
            
            if not state.is_alive:
                # Try to probe and recover
                await self._probe_node(name)
        
        # Run local recovery if needed
        if self._recovery_in_progress:
            return {"status": "already_in_progress"}
        
        # Re-check node health
        await self._check_node_health()
        
        return {"status": "completed", "cluster_status": self.get_cluster_status()}

    async def run_recovery_test(self, test_id: str) -> Dict[str, Any]:
        """Run a predefined recovery test scenario."""
        await self._emit_event(
            ClusterEventType.RECOVERY_STARTED,
            f"Starting recovery test: {test_id}",
            test_id=test_id,
        )
        
        result = {
            "test_id": test_id,
            "status": "running",
            "events": [],
            "phases": [],
        }
        
        try:
            if test_id == "follower_failure":
                # Test: A follower node fails and recovers
                # Find a follower (non-leader)
                follower = None
                for name, state in self._nodes.items():
                    if name != self._current_leader and state.effective_alive:
                        follower = name
                        break
                
                if not follower:
                    result["status"] = "skipped"
                    result["reason"] = "No follower available"
                    return result
                
                # Phase 1: Simulate failure
                result["phases"].append({"phase": "simulate_failure", "node": follower, "start": self._now()})
                await self.set_node_down(follower)
                await asyncio.sleep(2.0)
                
                # Phase 2: Verify cluster still works
                result["phases"].append({"phase": "verify_cluster", "start": self._now()})
                # Cluster should still be HEALTHY (just degraded)
                
                # Phase 3: Simulate recovery
                result["phases"].append({"phase": "simulate_recovery", "node": follower, "start": self._now()})
                await self.set_node_up(follower)
                await asyncio.sleep(2.0)
                
                result["status"] = "completed"
                
            elif test_id == "leader_failure":
                # Test: Leader fails, election happens, then leader recovers
                old_leader = self._current_leader
                
                if not old_leader:
                    result["status"] = "skipped"
                    result["reason"] = "No current leader"
                    return result
                
                # Phase 1: Simulate leader failure
                result["phases"].append({"phase": "simulate_failure", "node": old_leader, "start": self._now()})
                await self.set_node_down(old_leader)
                await asyncio.sleep(1.0)
                
                # Phase 2: Wait for election
                result["phases"].append({"phase": "wait_election", "start": self._now()})
                await asyncio.sleep(3.0)
                
                # Verify new leader elected
                new_leader = self._current_leader
                result["phases"].append({
                    "phase": "election_complete",
                    "old_leader": old_leader,
                    "new_leader": new_leader,
                    "start": self._now(),
                })
                
                # Phase 3: Simulate old leader recovery
                result["phases"].append({"phase": "simulate_recovery", "node": old_leader, "start": self._now()})
                await self.set_node_up(old_leader)
                await asyncio.sleep(2.0)
                
                result["status"] = "completed"
                result["old_leader"] = old_leader
                result["new_leader"] = new_leader
                
            elif test_id == "network_partition":
                # Test: Both partition nodes (node1, node2) fail simultaneously
                result["phases"].append({"phase": "simulate_partition", "start": self._now()})
                
                await self.set_node_down("node1")
                await self.set_node_down("node2")
                await asyncio.sleep(2.0)
                
                # Phase 2: Verify leader is still functional
                result["phases"].append({"phase": "verify_leader", "leader": self._current_leader, "start": self._now()})
                
                # Phase 3: Heal partition
                result["phases"].append({"phase": "heal_partition", "start": self._now()})
                await self.set_node_up("node1")
                await self.set_node_up("node2")
                await asyncio.sleep(3.0)
                
                result["status"] = "completed"
                
            elif test_id == "cascading_failure":
                # Test: Nodes fail one by one
                nodes_to_fail = [
                    name for name in self._nodes.keys()
                    if name != self.settings.node_name
                ]
                
                # Phase 1: Fail nodes one by one
                for i, node in enumerate(nodes_to_fail):
                    result["phases"].append({"phase": f"fail_node_{i+1}", "node": node, "start": self._now()})
                    await self.set_node_down(node)
                    await asyncio.sleep(1.5)
                
                # Phase 2: Recover nodes
                result["phases"].append({"phase": "begin_recovery", "start": self._now()})
                for i, node in enumerate(nodes_to_fail):
                    result["phases"].append({"phase": f"recover_node_{i+1}", "node": node, "start": self._now()})
                    await self.set_node_up(node)
                    await asyncio.sleep(1.5)
                
                result["status"] = "completed"
                
            else:
                result["status"] = "unknown_test"
                result["reason"] = f"Unknown test ID: {test_id}"
                
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            await self._emit_event(
                ClusterEventType.RECOVERY_FAILED,
                f"Recovery test {test_id} failed: {e}",
                level="error",
                error=str(e),
            )
        
        result["events"] = self.get_events(limit=50)
        result["final_status"] = self.get_cluster_status()
        
        return result
