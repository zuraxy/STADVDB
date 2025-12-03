"""API routes for cluster management and automatic recovery."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request, status, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio
import json
from datetime import datetime

router = APIRouter(prefix="/cluster", tags=["cluster"])


class HeartbeatPayload(BaseModel):
    """Heartbeat message from a peer node."""
    from_node: str
    lamport: int
    role: str
    leader: Optional[str] = None
    timestamp: str


class ElectionResultPayload(BaseModel):
    """Election result broadcast."""
    from_node: str
    new_leader: str
    lamport: int
    timestamp: str


class NodeControlRequest(BaseModel):
    """Request to control node state (on/off)."""
    node: str


class NodeToggleRequest(BaseModel):
    """Request to toggle node simulation state."""
    simulate_down: bool


class TestRunRequest(BaseModel):
    """Request to run a cluster test."""
    test_id: str


# ==================== Heartbeat & Election Endpoints ====================

@router.post("/heartbeat")
async def receive_heartbeat(payload: HeartbeatPayload, request: Request) -> Dict[str, Any]:
    """Receive heartbeat from a peer node."""
    cluster_manager = getattr(request.app.state, "cluster_manager", None)
    if not cluster_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cluster manager not initialized"
        )
    
    return await cluster_manager.handle_heartbeat(payload.dict())


@router.post("/election-result")
async def receive_election_result(payload: ElectionResultPayload, request: Request) -> Dict[str, Any]:
    """Receive election result broadcast."""
    cluster_manager = getattr(request.app.state, "cluster_manager", None)
    if not cluster_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cluster manager not initialized"
        )
    
    return await cluster_manager.handle_election_result(payload.dict())


# ==================== Node Control Endpoints ====================

@router.post("/node/down")
async def set_node_down(body: NodeControlRequest, request: Request) -> Dict[str, Any]:
    """Simulate a node going down (for testing)."""
    cluster_manager = getattr(request.app.state, "cluster_manager", None)
    if not cluster_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cluster manager not initialized"
        )
    
    success = await cluster_manager.set_node_down(body.node)
    return {
        "status": "success" if success else "failed",
        "node": body.node,
        "action": "down",
        "cluster_status": cluster_manager.get_cluster_status(),
    }


@router.post("/node/up")
async def set_node_up(body: NodeControlRequest, request: Request) -> Dict[str, Any]:
    """Simulate a node coming back online (triggers automatic recovery)."""
    cluster_manager = getattr(request.app.state, "cluster_manager", None)
    if not cluster_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cluster manager not initialized"
        )
    
    success = await cluster_manager.set_node_up(body.node)
    return {
        "status": "success" if success else "failed",
        "node": body.node,
        "action": "up",
        "cluster_status": cluster_manager.get_cluster_status(),
    }


@router.post("/node/{node_name}/toggle")
async def toggle_node(node_name: str, body: NodeToggleRequest, request: Request) -> Dict[str, Any]:
    """Toggle a node's simulated state (up/down)."""
    cluster_manager = getattr(request.app.state, "cluster_manager", None)
    if not cluster_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cluster manager not initialized"
        )
    
    if body.simulate_down:
        success = await cluster_manager.set_node_down(node_name)
        action = "down"
    else:
        success = await cluster_manager.set_node_up(node_name)
        action = "up"
    
    return {
        "node": node_name,
        "simulated_down": body.simulate_down,
        "status": "success" if success else "failed",
        "message": f"Node {node_name} marked as {'down' if body.simulate_down else 'up'}",
        "cluster_status": cluster_manager.get_cluster_status(),
    }


@router.post("/node/{node_name}/simulate-failure")
async def simulate_node_failure(node_name: str, request: Request) -> Dict[str, Any]:
    """Shorthand to simulate a node failure."""
    cluster_manager = getattr(request.app.state, "cluster_manager", None)
    if not cluster_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cluster manager not initialized"
        )
    
    success = await cluster_manager.set_node_down(node_name)
    return {
        "node": node_name,
        "simulated_down": True,
        "status": "success" if success else "failed",
        "message": f"Node {node_name} failure simulated",
        "cluster_status": cluster_manager.get_cluster_status(),
    }


@router.post("/node/{node_name}/simulate-recovery")
async def simulate_node_recovery(node_name: str, request: Request) -> Dict[str, Any]:
    """Shorthand to simulate a node recovery."""
    cluster_manager = getattr(request.app.state, "cluster_manager", None)
    if not cluster_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cluster manager not initialized"
        )
    
    success = await cluster_manager.set_node_up(node_name)
    return {
        "node": node_name,
        "simulated_down": False,
        "status": "success" if success else "failed",
        "message": f"Node {node_name} recovery simulated",
        "cluster_status": cluster_manager.get_cluster_status(),
    }


# ==================== Status & Events Endpoints ====================

@router.get("/status")
async def get_cluster_status(request: Request) -> Dict[str, Any]:
    """Get full cluster status including all nodes."""
    cluster_manager = getattr(request.app.state, "cluster_manager", None)
    if not cluster_manager:
        return {
            "error": "Cluster manager not initialized",
            "my_node": "unknown",
            "nodes": {},
            "state": "UNKNOWN",
            "leader": None,
            "health_summary": {
                "total_nodes": 0,
                "online_nodes": 0,
                "offline_nodes": 0,
            }
        }
    
    status = cluster_manager.get_cluster_status()
    
    # Calculate health summary
    nodes = status.get("nodes", {})
    online_count = sum(1 for n in nodes.values() if not n.get("simulated_down", False))
    
    status["health_summary"] = {
        "total_nodes": len(nodes),
        "online_nodes": online_count,
        "offline_nodes": len(nodes) - online_count,
    }
    
    return status


@router.get("/nodes")
async def get_node_states(request: Request) -> Dict[str, Any]:
    """Get all node states."""
    cluster_manager = getattr(request.app.state, "cluster_manager", None)
    if not cluster_manager:
        return {"nodes": {}}
    
    return {"nodes": cluster_manager.get_node_states()}


@router.get("/events")
async def get_cluster_events(
    request: Request,
    limit: int = 100,
    since_lamport: int = 0,
    event_type: Optional[str] = None
) -> Dict[str, Any]:
    """Get cluster events for timeline visualization."""
    cluster_manager = getattr(request.app.state, "cluster_manager", None)
    if not cluster_manager:
        return {"events": [], "latest_lamport": 0}
    
    events = cluster_manager.get_events(limit=limit, since_lamport=since_lamport)
    
    # Filter by event type if specified
    if event_type:
        events = [e for e in events if e.get("event_type") == event_type]
    
    return {
        "events": events,
        "latest_lamport": events[-1]["lamport_time"] if events else since_lamport,
    }


@router.get("/timeline")
async def get_cluster_timeline(
    request: Request,
    duration_seconds: int = 60
) -> Dict[str, Any]:
    """Get cluster timeline for visualization."""
    cluster_manager = getattr(request.app.state, "cluster_manager", None)
    if not cluster_manager:
        return {"timeline": [], "current_time": datetime.utcnow().isoformat()}
    
    events = cluster_manager.get_events(limit=200)
    
    # Convert events to timeline format
    timeline = []
    now = datetime.utcnow()
    cutoff = now.timestamp() - duration_seconds
    
    for event in events:
        try:
            event_time = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
            if event_time.timestamp() >= cutoff:
                timeline.append({
                    "timestamp": event["timestamp"],
                    "event_type": event["event_type"],
                    "node": event.get("node", "unknown"),
                    "message": event.get("message", ""),
                    "relative_time": now.timestamp() - event_time.timestamp(),
                })
        except (KeyError, ValueError):
            continue
    
    return {
        "timeline": timeline,
        "current_time": now.isoformat(),
        "duration_seconds": duration_seconds,
    }


@router.get("/events/stream")
async def stream_cluster_events(request: Request) -> StreamingResponse:
    """SSE stream of cluster events for real-time updates."""
    cluster_manager = getattr(request.app.state, "cluster_manager", None)
    
    async def event_generator():
        """Generate SSE events."""
        if not cluster_manager:
            yield f"data: {json.dumps({'error': 'Cluster manager not initialized'})}\n\n"
            return
        
        last_lamport = 0
        queue = asyncio.Queue()
        
        # Add callback for new events
        def on_event(event):
            queue.put_nowait(event)
        
        cluster_manager.add_event_callback(on_event)
        
        try:
            # Send initial events
            events = cluster_manager.get_events(limit=50)
            for event in events:
                yield f"data: {json.dumps(event)}\n\n"
                last_lamport = event["lamport_time"]
            
            # Stream new events
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(event.to_dict() if hasattr(event, 'to_dict') else event)}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield f": keepalive\n\n"
        finally:
            cluster_manager.remove_event_callback(on_event)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# ==================== Recovery Status Endpoints ====================

@router.get("/recovery/status")
async def get_recovery_status(request: Request) -> Dict[str, Any]:
    """Get current recovery status."""
    cluster_manager = getattr(request.app.state, "cluster_manager", None)
    if not cluster_manager:
        return {"recovery_in_progress": False, "writes_allowed": True}
    
    status = cluster_manager.get_cluster_status()
    return {
        "recovery_in_progress": status["recovery_in_progress"],
        "writes_gated": status["writes_gated"],
        "writes_allowed": status["writes_allowed"],
        "election_in_progress": status["election_in_progress"],
        "current_leader": status["current_leader"],
    }


@router.post("/recovery/trigger")
async def trigger_cluster_recovery(request: Request) -> Dict[str, Any]:
    """Manually trigger automatic recovery (force refresh)."""
    cluster_manager = getattr(request.app.state, "cluster_manager", None)
    if not cluster_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cluster manager not initialized"
        )
    
    # Force a recovery check cycle
    await cluster_manager._trigger_automatic_recovery()
    
    return {
        "status": "triggered",
        "message": "Recovery cycle triggered",
        "cluster_status": cluster_manager.get_cluster_status(),
    }


@router.get("/writes/allowed")
async def check_writes_allowed(request: Request) -> Dict[str, Any]:
    """Check if writes are currently allowed."""
    cluster_manager = getattr(request.app.state, "cluster_manager", None)
    if not cluster_manager:
        return {"allowed": True, "reason": None}
    
    allowed = cluster_manager.writes_allowed
    reason = None
    if not allowed:
        status = cluster_manager.get_cluster_status()
        if status["election_in_progress"]:
            reason = "Election in progress"
        elif status["recovery_in_progress"]:
            reason = "Recovery in progress"
        elif status["writes_gated"]:
            reason = "Writes gated"
    
    return {"allowed": allowed, "reason": reason}


# ==================== Test Scenario Endpoints ====================

# Define the 4 correct test cases
TEST_CASES = {
    "case_1": {
        "id": "case_1",
        "name": "Follower Write → Downed Leader",
        "description": "Write from Node2/Node3 (follower) fails to replicate to Node0 (leader) because leader is down",
        "scenario": "Demonstrates replication failure when the leader is unavailable",
        "expected": "Writes from followers should fail with 503 (leader unreachable)",
    },
    "case_2": {
        "id": "case_2",
        "name": "Leader Catches Up",
        "description": "Node0 (leader) comes back online and pulls missed oplogs to catch up",
        "scenario": "Recovery after leader failure - leader syncs missed writes",
        "expected": "Leader should recover and sync any writes that happened during downtime",
    },
    "case_3": {
        "id": "case_3",
        "name": "Leader Write → Downed Followers",
        "description": "Write from Node0 (leader) fails to replicate to Node2/Node3 (followers) because they are down",
        "scenario": "Demonstrates replication lag when followers are unavailable",
        "expected": "Writes accepted locally on leader, oplogs queued for replication",
    },
    "case_4": {
        "id": "case_4",
        "name": "Followers Catch Up",
        "description": "Node2/Node3 (followers) come back online and catch up with oplogs",
        "scenario": "Recovery after follower failure - followers sync missed writes",
        "expected": "Followers should recover and pull all queued oplogs from leader",
    },
}


class RecoveryTestRequest(BaseModel):
    """Request to run a recovery test scenario."""
    scenario: str  # "leader_failure", "follower_failure", "partition_heal", "network_partition"
    target_node: Optional[str] = None
    duration_seconds: Optional[float] = 5.0


# Track running tests
_current_test: Optional[Dict] = None
_test_history: List[Dict] = []


@router.get("/test/cases")
async def get_test_cases(request: Request) -> Dict[str, Any]:
    """Get list of available recovery test cases."""
    return {
        "cases": list(TEST_CASES.values()),
        "description": "Recovery test cases demonstrating replication failure and catch-up scenarios"
    }


@router.post("/test/run")
async def run_cluster_test(body: TestRunRequest, request: Request) -> Dict[str, Any]:
    """Run a cluster recovery test by test_id."""
    global _current_test, _test_history
    
    cluster_manager = getattr(request.app.state, "cluster_manager", None)
    if not cluster_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cluster manager not initialized"
        )
    
    if _current_test and _current_test.get("status") == "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A test is already running"
        )
    
    test_id = body.test_id
    _current_test = {
        "test_id": test_id,
        "status": "running",
        "started_at": datetime.utcnow().isoformat(),
        "events": [],
    }
    
    try:
        result = await cluster_manager.run_recovery_test(test_id)
        _current_test["status"] = result.get("status", "completed")
        _current_test["result"] = result
        _current_test["completed_at"] = datetime.utcnow().isoformat()
        _current_test["events"] = cluster_manager.get_events(limit=50)
    except Exception as e:
        _current_test["status"] = "failed"
        _current_test["error"] = str(e)
        _current_test["completed_at"] = datetime.utcnow().isoformat()
    
    # Add to history
    _test_history.append(_current_test.copy())
    
    return {
        "test_id": test_id,
        "status": _current_test["status"],
        "message": f"Test {test_id} completed",
    }


@router.get("/test/current")
async def get_current_test(request: Request) -> Dict[str, Any]:
    """Get currently running test."""
    return {"current_test": _current_test}


@router.get("/test/history")
async def get_test_history(request: Request) -> Dict[str, Any]:
    """Get test history."""
    return {"history": _test_history[-20:]}  # Last 20 tests


@router.post("/test/scenario")
async def run_recovery_scenario(body: RecoveryTestRequest, request: Request) -> Dict[str, Any]:
    """Run a pre-defined recovery test scenario."""
    cluster_manager = getattr(request.app.state, "cluster_manager", None)
    if not cluster_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cluster manager not initialized"
        )
    
    result = {
        "scenario": body.scenario,
        "target_node": body.target_node,
        "events": [],
        "status": "completed",
    }
    
    try:
        if body.scenario == "leader_failure":
            # Simulate leader failure
            leader = cluster_manager.current_leader
            if leader:
                await cluster_manager.set_node_down(leader)
                await asyncio.sleep(body.duration_seconds)
                await cluster_manager.set_node_up(leader)
                result["events"] = cluster_manager.get_events(limit=20)
        
        elif body.scenario == "follower_failure":
            # Simulate a follower failure
            target = body.target_node or "node1"
            if target != cluster_manager.current_leader:
                await cluster_manager.set_node_down(target)
                await asyncio.sleep(body.duration_seconds)
                await cluster_manager.set_node_up(target)
                result["events"] = cluster_manager.get_events(limit=20)
        
        elif body.scenario == "partition_heal":
            # Simulate partition nodes failing and recovering
            await cluster_manager.set_node_down("node1")
            await cluster_manager.set_node_down("node2")
            await asyncio.sleep(body.duration_seconds / 2)
            await cluster_manager.set_node_up("node1")
            await cluster_manager.set_node_up("node2")
            await asyncio.sleep(body.duration_seconds / 2)
            result["events"] = cluster_manager.get_events(limit=30)
        
        elif body.scenario == "full_recovery":
            # Test full cluster recovery sequence
            all_nodes = list(cluster_manager.get_node_states().keys())
            # Take all non-local nodes down
            for node in all_nodes:
                if node != cluster_manager.settings.node_name:
                    await cluster_manager.set_node_down(node)
            
            await asyncio.sleep(body.duration_seconds / 2)
            
            # Bring them back up
            for node in all_nodes:
                if node != cluster_manager.settings.node_name:
                    await cluster_manager.set_node_up(node)
            
            await asyncio.sleep(body.duration_seconds / 2)
            result["events"] = cluster_manager.get_events(limit=40)
        
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown scenario: {body.scenario}"
            )
        
        result["final_cluster_status"] = cluster_manager.get_cluster_status()
        
    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
    
    return result
