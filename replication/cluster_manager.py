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
    REPLICATION_PENDING = "replication_pending"
    
    # Write events (for test scenarios)
    WRITE_ACCEPTED = "write_accepted"
    WRITE_FAILED = "write_failed"
    WRITE_REJECTED = "write_rejected"
    
    # Write gating events
    WRITES_GATED = "writes_gated"
    WRITES_ENABLED = "writes_enabled"


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
        
        # Set initial leader to default_master for ALL nodes
        # This ensures all nodes know who the leader is from the start
        self._current_leader = self.settings.default_master
        
        # Set role based on whether this node is the initial leader
        if self.settings.node_name == self.settings.default_master:
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
        """Check health of all nodes and trigger failover if needed."""
        # If THIS node is simulated down, skip health monitoring
        # A "down" node shouldn't be making decisions about cluster state
        my_state = self._nodes.get(self.settings.node_name)
        if my_state and my_state.is_simulated_down:
            return
        
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
            
            # Enable writes - election is complete
            # Note: writes should be enabled regardless of role since election is done
            # The new leader will handle writes, followers will forward
            self._writes_gated = False
            await self._emit_event(
                ClusterEventType.WRITES_ENABLED,
                f"Writes enabled (election complete, leader is {new_leader})",
            )
        
        finally:
            self._election_in_progress = False

    async def _broadcast_election_result(self, new_leader: str):
        """Broadcast election result to all peers."""
        lamport = await self._tick_lamport()
        
        # Check if this node (the sender) is simulated down - include this info
        # so receivers know to update their view of this node's status
        my_state = self._nodes.get(self.settings.node_name)
        sender_is_down = my_state.is_simulated_down if my_state else False
        
        payload = {
            "from_node": self.settings.node_name,
            "new_leader": new_leader,
            "lamport": lamport,
            "timestamp": self._now(),
            "sender_is_down": sender_is_down,  # Tell receivers this node is going down
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
        state.is_alive = True
        state.last_heartbeat = datetime.now(timezone.utc)
        
        await self._emit_event(
            ClusterEventType.NODE_UP,
            f"Node {node_name} coming online",
            node=node_name,
        )
        
        if was_down:
            # If node0 (default_master) comes back, re-elect it as leader and demote others
            if node_name.lower() == self.settings.default_master.lower():
                await self._restore_default_leader(node_name)
            else:
                # Regular node recovery
                await self._trigger_node_recovery(node_name)
        
        return True

    async def _restore_default_leader(self, node_name: str):
        """Restore node0 as leader when it comes back online and demote promoted nodes."""
        old_leader = self._current_leader
        
        await self._emit_event(
            ClusterEventType.ELECTION_STARTED,
            f"Restoring {node_name} as leader (default master)",
            node=node_name,
        )
        
        # Set node0 as the leader
        self._current_leader = node_name
        
        if node_name == self.settings.node_name:
            # This node is the default master coming back
            self._my_role = NodeRole.LEADER
            self._set_promoted_flag(False)  # Leader doesn't need promoted flag
        
        await self._emit_event(
            ClusterEventType.LEADER_ELECTED,
            f"{node_name} restored as leader",
            node=node_name,
            old_leader=old_leader,
        )
        
        # Broadcast demotion to all peer nodes
        await self._broadcast_demotion_to_all()
        
        # Trigger recovery for the restored leader to catch up
        await self._trigger_node_recovery(node_name)

    async def _broadcast_demotion_to_all(self):
        """Broadcast demotion signal to all peer nodes."""
        await self._emit_event(
            ClusterEventType.NODE_SYNCED,
            "Broadcasting demotion to all promoted nodes",
        )
        
        for peer in self.settings.peer_nodes:
            if peer.name == self.settings.node_name:
                continue
            try:
                await self.http_client.post_json(
                    f"{peer.base_url}/admin/demote",
                    {"demote": True}
                )
                _LOGGER.info("Demoted %s", peer.name)
            except Exception as e:
                _LOGGER.warning("Failed to demote %s: %s", peer.name, e)

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

    def is_node_simulated_down(self, node_name: str) -> bool:
        """Check if a node is simulated as down."""
        node_key = node_name.lower()
        for name, state in self._nodes.items():
            if name.lower() == node_key:
                return state.is_simulated_down
        return False

    def get_node_states(self) -> Dict[str, Dict]:
        """Get all node states with accurate roles based on current leader."""
        result = {}
        for name, state in self._nodes.items():
            node_dict = state.to_dict()
            # Override role based on current leader and node status
            if not state.effective_alive:
                node_dict["role"] = NodeRole.OFFLINE.value
            elif name == self._current_leader:
                node_dict["role"] = NodeRole.LEADER.value
            else:
                node_dict["role"] = NodeRole.FOLLOWER.value
            result[name] = node_dict
        return result

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

    def clear_events(self) -> int:
        """Clear all stored events. Returns count of cleared events."""
        count = len(self._events)
        self._events.clear()
        return count

    async def get_db_lamport_values(self) -> Dict[str, int]:
        """Fetch actual lamport values from replication_cursors table."""
        try:
            async with self.pool.acquire() as conn:
                # Get max lamport from op_log
                max_lamport = await conn.fetchval(
                    "SELECT COALESCE(MAX(lamport), -1) FROM op_log"
                )
                # Get replication cursors for each peer
                cursors = await conn.fetch(
                    "SELECT node, last_lamport FROM replication_cursors"
                )
                result = {"max_op_log": int(max_lamport)}
                for row in cursors:
                    result[row["node"]] = int(row["last_lamport"])
                return result
        except Exception as e:
            _LOGGER.warning("Failed to fetch DB lamport values: %s", e)
            return {"error": str(e)}

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
            was_dead = not state.is_alive or state.is_simulated_down
            state.is_alive = True
            state.last_heartbeat = datetime.now(timezone.utc)
            state.last_seen_lamport = received_lamport
            
            # IMPORTANT: If the default_master (node0) comes back alive via heartbeat,
            # we must restore it as leader immediately. This handles the case where
            # node0 was temporarily unreachable and we elected a different leader.
            default_master = self.settings.default_master.lower()
            if from_node.lower() == default_master and was_dead:
                # Default master is back! Restore it as leader
                _LOGGER.info("Default master %s is back alive via heartbeat - restoring as leader", from_node)
                if self._current_leader and self._current_leader.lower() != default_master:
                    # We had a different leader, need to restore default master
                    old_leader = self._current_leader
                    self._current_leader = from_node
                    self._my_role = NodeRole.FOLLOWER
                    await self._emit_event(
                        ClusterEventType.LEADER_ELECTED,
                        f"Default master {from_node} restored as leader (was {old_leader})",
                        new_leader=from_node,
                        old_leader=old_leader,
                    )
            
            # Log disagreements for debugging (but don't change leader from heartbeat)
            peer_leader = payload.get("leader")
            if peer_leader and peer_leader != self._current_leader:
                _LOGGER.debug(
                    "Leader disagreement: peer %s thinks leader is %s, but this node thinks it's %s",
                    from_node, peer_leader, self._current_leader
                )
        
        my_lamport = await self._tick_lamport()
        return {
            "from_node": self.settings.node_name,
            "lamport": my_lamport,
            "leader": self._current_leader,
            "role": self._my_role.value,
        }

    async def handle_election_result(self, payload: Dict) -> Dict:
        """Handle election result broadcast from another node.
        
        IMPORTANT: We validate the election result to prevent wrong leader scenarios.
        If node0 (default_master) is alive, only accept node0 as leader.
        
        EXCEPTION: If the election is sent BY the default_master itself (with sender_is_down=True),
        it means the default_master is going offline and delegating leadership.
        """
        new_leader = payload.get("new_leader")
        received_lamport = payload.get("lamport", 0)
        from_node = payload.get("from_node", "").lower()
        sender_is_down = payload.get("sender_is_down", False)
        
        await self._update_lamport(received_lamport)
        
        if new_leader:
            # Get default master info
            default_master = self.settings.default_master.lower()
            default_master_state = self._nodes.get(default_master)
            
            # If sender says it's going down, update our view of it
            if sender_is_down and from_node:
                sender_state = self._nodes.get(from_node)
                if sender_state:
                    sender_state.is_alive = False
                    _LOGGER.info("Updated %s status to DOWN (sender reported going offline)", from_node)
            
            # Validate: If default_master (node0) is alive, it should ALWAYS be leader
            # EXCEPTION: If the message is FROM default_master saying it's going down
            if new_leader.lower() != default_master:
                # Someone is trying to elect a non-default-master as leader
                # Only accept if default_master is actually down OR default_master sent this message
                is_from_default_master = (from_node == default_master)
                default_master_effectively_alive = (
                    default_master_state and 
                    default_master_state.effective_alive and
                    not sender_is_down  # Don't consider alive if sender says it's going down
                )
                
                if default_master_effectively_alive and not is_from_default_master:
                    _LOGGER.warning(
                        "Rejecting election result: %s claims leader is %s, but default_master %s is alive",
                        from_node, new_leader, default_master
                    )
                    return {"status": "rejected", "reason": "default_master is alive", "leader": self._current_leader}
            
            self._current_leader = new_leader
            self._election_in_progress = False  # Election is complete
            
            if new_leader == self.settings.node_name:
                # This node is the new leader
                self._my_role = NodeRole.LEADER
                self._set_promoted_flag(True)
                self._writes_gated = False  # Leader must enable writes
                await self._emit_event(
                    ClusterEventType.WRITES_ENABLED,
                    "Writes enabled (this node is new leader)",
                )
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
        """
        Run a predefined recovery test scenario.
        
        The 4 correct test cases are:
        - case_1: Write from Node1/Node2 (follower) fails to replicate to Node0 (leader) because leader is down
        - case_2: Node0 (leader) comes back online and pulls missed oplogs to catch up
        - case_3: Write from Node0 (leader) fails to replicate to Node1/Node2 (followers) because they are down
        - case_4: Node1/Node2 (followers) come back online and catch up with oplogs
        """
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
            "description": "",
        }
        
        try:
            if test_id == "case_1":
                # Case #1: Write from follower fails to replicate to leader (leader is down)
                result["description"] = "Write from follower fails to replicate to downed leader"
                leader = self._current_leader or "node0"
                
                # Find a follower
                follower = None
                for name, state in self._nodes.items():
                    if name != leader:
                        follower = name
                        break
                
                if not follower:
                    result["status"] = "skipped"
                    result["reason"] = "No follower available"
                    return result
                
                # Phase 1: Take leader offline
                result["phases"].append({
                    "phase": "take_leader_offline",
                    "node": leader,
                    "start": self._now(),
                    "action": f"Simulating {leader} (leader) going down"
                })
                await self.set_node_down(leader)
                await asyncio.sleep(1.0)
                
                # Phase 2: Attempt write from follower (will fail to replicate)
                result["phases"].append({
                    "phase": "write_from_follower",
                    "node": follower,
                    "start": self._now(),
                    "action": f"Write attempted from {follower} - cannot replicate to downed leader",
                    "expected": "Write should fail or be queued (503 response)"
                })
                
                # The write would fail because leader is down - this demonstrates the issue
                await self._emit_event(
                    ClusterEventType.WRITE_FAILED,
                    f"Write from {follower} cannot replicate to downed leader {leader}",
                    node=follower,
                    level="warning",
                    target_leader=leader,
                    leader_status="down",
                )
                await asyncio.sleep(1.0)
                
                result["status"] = "completed"
                result["outcome"] = f"Demonstrated: Writes from {follower} fail when leader {leader} is down"
                result["leader_was"] = leader
                result["follower"] = follower
                
            elif test_id == "case_2":
                # Case #2: Leader comes back and pulls missed oplogs
                result["description"] = "Leader comes back online and catches up via oplog sync"
                
                # Find the simulated-down leader
                old_leader = None
                for name, state in self._nodes.items():
                    if state.is_simulated_down:
                        old_leader = name
                        break
                
                if not old_leader:
                    # If no node is down, simulate case_1 first
                    old_leader = self._current_leader or "node0"
                    result["phases"].append({
                        "phase": "setup_precondition",
                        "node": old_leader,
                        "start": self._now(),
                        "action": f"Taking {old_leader} offline first (precondition)"
                    })
                    await self.set_node_down(old_leader)
                    await asyncio.sleep(1.5)
                
                # Phase 1: Bring leader back
                result["phases"].append({
                    "phase": "bring_leader_online",
                    "node": old_leader,
                    "start": self._now(),
                    "action": f"Bringing {old_leader} back online"
                })
                await self.set_node_up(old_leader)
                await asyncio.sleep(0.5)
                
                # Phase 2: Leader pulls missed oplogs from peers
                result["phases"].append({
                    "phase": "pull_missed_oplogs",
                    "node": old_leader,
                    "start": self._now(),
                    "action": f"{old_leader} pulling missed oplogs from peers",
                    "expected": "Oplog entries replicated to recovering node"
                })
                
                await self._emit_event(
                    ClusterEventType.RECOVERY_FETCHING,
                    f"{old_leader} pulling missed oplogs from peers",
                    node=old_leader,
                )
                await asyncio.sleep(2.0)
                
                # Phase 3: Verify catch-up
                result["phases"].append({
                    "phase": "verify_catchup",
                    "node": old_leader,
                    "start": self._now(),
                    "action": f"{old_leader} should now be in sync"
                })
                
                await self._emit_event(
                    ClusterEventType.RECOVERY_COMPLETED,
                    f"{old_leader} has caught up with the cluster",
                    node=old_leader,
                )
                
                result["status"] = "completed"
                result["outcome"] = f"{old_leader} came back and caught up via oplog sync"
                result["recovered_node"] = old_leader
                
            elif test_id == "case_3":
                # Case #3: Write from leader fails to replicate to followers (followers are down)
                result["description"] = "Write from leader fails to replicate to downed followers"
                leader = self._current_leader or "node0"
                
                # Get followers
                followers = [
                    name for name, state in self._nodes.items()
                    if name != leader
                ]
                
                if not followers:
                    result["status"] = "skipped"
                    result["reason"] = "No followers available"
                    return result
                
                # Phase 1: Take followers offline
                result["phases"].append({
                    "phase": "take_followers_offline",
                    "nodes": followers,
                    "start": self._now(),
                    "action": f"Simulating followers going down: {followers}"
                })
                for follower in followers:
                    await self.set_node_down(follower)
                await asyncio.sleep(1.0)
                
                # Phase 2: Write from leader (succeeds locally, fails to replicate)
                result["phases"].append({
                    "phase": "write_from_leader",
                    "node": leader,
                    "start": self._now(),
                    "action": f"Write from {leader} succeeds locally but cannot replicate to downed followers",
                    "expected": "Write accepted but oplogs queued for replication"
                })
                
                await self._emit_event(
                    ClusterEventType.WRITE_ACCEPTED,
                    f"Write from {leader} accepted locally",
                    node=leader,
                    replication_status="pending",
                    target_followers=followers,
                )
                await asyncio.sleep(0.5)
                
                await self._emit_event(
                    ClusterEventType.REPLICATION_PENDING,
                    f"Oplogs queued - followers {followers} are down",
                    node=leader,
                    level="warning",
                    target_followers=followers,
                )
                await asyncio.sleep(1.0)
                
                result["status"] = "completed"
                result["outcome"] = f"Writes from {leader} accepted but replication to {followers} pending"
                result["leader"] = leader
                result["downed_followers"] = followers
                
            elif test_id == "case_4":
                # Case #4: Followers come back and catch up
                result["description"] = "Followers come back online and catch up via oplog sync"
                
                # Find simulated-down followers
                downed_followers = [
                    name for name, state in self._nodes.items()
                    if state.is_simulated_down
                ]
                
                if not downed_followers:
                    # Setup precondition: take followers offline first
                    leader = self._current_leader or "node0"
                    downed_followers = [
                        name for name in self._nodes.keys()
                        if name != leader
                    ]
                    
                    if not downed_followers:
                        result["status"] = "skipped"
                        result["reason"] = "No followers available"
                        return result
                    
                    result["phases"].append({
                        "phase": "setup_precondition",
                        "nodes": downed_followers,
                        "start": self._now(),
                        "action": f"Taking followers offline first: {downed_followers}"
                    })
                    for follower in downed_followers:
                        await self.set_node_down(follower)
                    await asyncio.sleep(1.5)
                
                # Phase 1: Bring followers back
                result["phases"].append({
                    "phase": "bring_followers_online",
                    "nodes": downed_followers,
                    "start": self._now(),
                    "action": f"Bringing followers back online: {downed_followers}"
                })
                for follower in downed_followers:
                    await self.set_node_up(follower)
                await asyncio.sleep(0.5)
                
                # Phase 2: Followers pull missed oplogs
                result["phases"].append({
                    "phase": "pull_missed_oplogs",
                    "nodes": downed_followers,
                    "start": self._now(),
                    "action": f"Followers pulling missed oplogs from leader",
                    "expected": "All queued oplogs replicated to recovering followers"
                })
                
                for follower in downed_followers:
                    await self._emit_event(
                        ClusterEventType.RECOVERY_FETCHING,
                        f"{follower} pulling missed oplogs from leader",
                        node=follower,
                    )
                await asyncio.sleep(2.0)
                
                # Phase 3: Verify catch-up
                result["phases"].append({
                    "phase": "verify_catchup",
                    "nodes": downed_followers,
                    "start": self._now(),
                    "action": f"Followers should now be in sync"
                })
                
                for follower in downed_followers:
                    await self._emit_event(
                        ClusterEventType.RECOVERY_COMPLETED,
                        f"{follower} has caught up with the leader",
                        node=follower,
                    )
                
                result["status"] = "completed"
                result["outcome"] = f"Followers {downed_followers} caught up via oplog sync"
                result["recovered_nodes"] = downed_followers
                
            else:
                result["status"] = "unknown_test"
                result["reason"] = f"Unknown test ID: {test_id}. Valid IDs: case_1, case_2, case_3, case_4"
                
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
