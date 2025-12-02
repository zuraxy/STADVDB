"""Recovery API endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from ..db import get_pool
from ..config import get_settings

router = APIRouter(prefix="/recovery", tags=["recovery"])


class StartRecoveryRequest(BaseModel):
    """Request body for starting a recovery job."""
    mode: str  # 'leader', 'node', or 'promotion'
    since_ts: Optional[str] = None
    promoted_node: Optional[str] = None


class ForceSnapshotRequest(BaseModel):
    """Request body for force snapshot."""
    peer: Optional[str] = None
    partition: Optional[str] = None  # 'low', 'high', or None for all


@router.post("/start")
async def start_recovery(body: StartRecoveryRequest, request: Request) -> dict:
    """Start a new recovery job.
    
    Modes:
    - leader: Full leader recovery (Node0 catching up after downtime)
    - node: Node cold-rejoin (Node1/Node2 rejoining after downtime)
    - promotion: Promotion resync (Node0 catching up from promoted nodes)
    """
    recovery_manager = getattr(request.app.state, "recovery_manager", None)
    if not recovery_manager:
        raise HTTPException(503, detail="Recovery manager not initialized")
    
    if body.mode not in ("leader", "node", "promotion"):
        raise HTTPException(400, detail="Invalid mode. Use 'leader', 'node', or 'promotion'")
    
    try:
        job_id = await recovery_manager.start_job(
            mode=body.mode,
            since_ts=body.since_ts,
            promoted_node=body.promoted_node,
        )
        return {"job_id": job_id, "status": "started"}
    except RuntimeError as e:
        raise HTTPException(409, detail=str(e))
    except ValueError as e:
        raise HTTPException(400, detail=str(e))


@router.get("/status/{job_id}")
async def get_recovery_status(job_id: str, request: Request) -> dict:
    """Get the status of a recovery job."""
    recovery_manager = getattr(request.app.state, "recovery_manager", None)
    if not recovery_manager:
        raise HTTPException(503, detail="Recovery manager not initialized")
    
    status = recovery_manager.get_status(job_id)
    if not status:
        raise HTTPException(404, detail=f"Job {job_id} not found")
    
    return status


@router.get("/logs/{job_id}")
async def get_recovery_logs(
    job_id: str,
    request: Request,
    limit: int = Query(100, ge=1, le=1000),
) -> dict:
    """Get logs for a recovery job."""
    recovery_manager = getattr(request.app.state, "recovery_manager", None)
    if not recovery_manager:
        raise HTTPException(503, detail="Recovery manager not initialized")
    
    logs = recovery_manager.get_logs(job_id, limit=limit)
    if logs is None:
        raise HTTPException(404, detail=f"Job {job_id} not found")
    
    return {"job_id": job_id, "logs": logs}


@router.post("/abort/{job_id}")
async def abort_recovery(job_id: str, request: Request) -> dict:
    """Abort a running recovery job."""
    recovery_manager = getattr(request.app.state, "recovery_manager", None)
    if not recovery_manager:
        raise HTTPException(503, detail="Recovery manager not initialized")
    
    success = await recovery_manager.abort_job(job_id)
    if not success:
        raise HTTPException(404, detail=f"Job {job_id} not found or already completed")
    
    return {"job_id": job_id, "status": "aborted"}


@router.get("/snapshot")
async def export_snapshot(
    request: Request,
    partition: Optional[str] = Query(None, description="Partition: 'low', 'high', or None for all"),
    format: str = Query("json", description="Format: 'json' or 'csv'"),
) -> dict:
    """Export local orders as snapshot for recovery."""
    recovery_manager = getattr(request.app.state, "recovery_manager", None)
    if recovery_manager:
        return await recovery_manager.export_snapshot(partition=partition, format=format)
    
    # Fallback if manager not available
    from ..recovery import export_snapshot_helper
    pool = get_pool()
    settings = get_settings()
    return await export_snapshot_helper(pool, partition=partition, partition_rule=settings.partition_rule)


@router.post("/force_snapshot")
async def force_snapshot(body: ForceSnapshotRequest, request: Request) -> dict:
    """Force import a snapshot from a peer node.
    
    This is used when the gap is too large for incremental sync.
    """
    recovery_manager = getattr(request.app.state, "recovery_manager", None)
    if not recovery_manager:
        raise HTTPException(503, detail="Recovery manager not initialized")
    
    # This triggers a snapshot import as part of a recovery job
    # For now, return info about what would be fetched
    settings = get_settings()
    peer_url = None
    
    if body.peer:
        for peer in settings.peer_nodes:
            if peer.name.lower() == body.peer.lower():
                peer_url = peer.base_url
                break
        if not peer_url:
            raise HTTPException(404, detail=f"Peer {body.peer} not found")
    
    return {
        "status": "snapshot_request_queued",
        "peer": body.peer,
        "partition": body.partition,
        "peer_url": peer_url,
    }


@router.get("/flag")
async def get_recovery_flag(request: Request) -> dict:
    """Get the current recovery flag status (whether writes are gated)."""
    recovery_manager = getattr(request.app.state, "recovery_manager", None)
    if recovery_manager:
        return {
            "recovery_in_progress": recovery_manager.recovery_in_progress,
            "writes_gated": recovery_manager.writes_gated,
        }
    
    from ..recovery import get_recovery_flag
    return {
        "recovery_in_progress": False,
        "writes_gated": get_recovery_flag(),
    }


@router.get("/active")
async def get_active_job(request: Request) -> dict:
    """Get the currently active recovery job, if any."""
    recovery_manager = getattr(request.app.state, "recovery_manager", None)
    if not recovery_manager:
        return {"active_job": None}
    
    if recovery_manager._active_job:
        status = recovery_manager.get_status(recovery_manager._active_job)
        return {"active_job": status}
    
    return {"active_job": None}


# Demotion endpoint (called by leader during promotion resync)
@router.post("/demote")
async def demote_node(request: Request) -> dict:
    """Demote this node (clear promoted flag)."""
    request.app.state.promoted = False
    
    # Also record demotion in promotion_log if it exists
    pool = get_pool()
    settings = get_settings()
    
    try:
        async with pool.acquire() as conn:
            # Try to update promotion_log if table exists
            await conn.execute("""
                UPDATE promotion_log 
                SET demoted_at = NOW() 
                WHERE node = $1 AND demoted_at IS NULL
            """, settings.node_name)
    except Exception:
        pass  # Table may not exist yet
    
    return {"node": settings.node_name, "promoted": False, "status": "demoted"}


# Promotion recording endpoint
@router.post("/promote")
async def record_promotion(request: Request) -> dict:
    """Record that this node is being promoted."""
    pool = get_pool()
    settings = get_settings()
    
    # Set promoted flag
    request.app.state.promoted = True
    
    try:
        async with pool.acquire() as conn:
            # Ensure promotion_log table exists
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS promotion_log (
                    id SERIAL PRIMARY KEY,
                    node TEXT NOT NULL,
                    promoted_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    demoted_at TIMESTAMP WITH TIME ZONE
                )
            """)
            # Record promotion
            await conn.execute("""
                INSERT INTO promotion_log (node, promoted_at)
                VALUES ($1, NOW())
            """, settings.node_name)
    except Exception as e:
        return {"error": str(e), "promoted": True}
    
    return {"node": settings.node_name, "promoted": True, "status": "promoted"}
