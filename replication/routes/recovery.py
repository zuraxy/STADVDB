"""Recovery API Router.

This module provides the FastAPI endpoints for the Recovery Subsystem.
Endpoints:
- POST /recovery/start - Start a recovery job
- GET /recovery/status/{job_id} - Get recovery job status
- GET /recovery/logs/{job_id} - Stream recovery logs
- GET /recovery/health - Get node health status
- POST /recovery/snapshot - Force a snapshot/resync
- GET /recovery/gap - Get sync gap with peers
- GET /recovery/dashboard - Serve the recovery dashboard
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from ..workers.recovery_manager import RecoveryManager, RecoveryMode, RecoveryState

router = APIRouter(prefix="/recovery", tags=["recovery"])


# --- Pydantic Models ---

class RecoveryStartRequest(BaseModel):
    """Request body for starting recovery."""
    mode: str = Field(
        default="leader",
        description="Recovery mode: 'leader' for Node0 recovery, 'node' for replica promotion"
    )


class RecoveryStartResponse(BaseModel):
    """Response for recovery start."""
    job_id: str
    mode: str
    message: str


class RecoveryProgressResponse(BaseModel):
    """Progress metrics for a recovery job."""
    state: str
    mode: str
    ops_fetched: int
    ops_merged: int
    ops_applied: int
    ops_remaining: int
    ops_skipped: int
    ops_conflicted: int
    peers_contacted: int
    peers_failed: int
    start_time: Optional[str]
    end_time: Optional[str]
    last_error: Optional[str]
    local_lamport_start: int
    local_lamport_end: int


class RecoveryStatusResponse(BaseModel):
    """Full status response for a recovery job."""
    job_id: str
    is_running: bool
    progress: RecoveryProgressResponse


class NodeHealthResponse(BaseModel):
    """Node health status."""
    node: str
    state: str
    is_ready: bool
    local_stats: Dict[str, Any]
    peers: List[Dict[str, Any]]


class SyncGapResponse(BaseModel):
    """Sync gap between nodes."""
    local_max_lamport: int
    gaps: Dict[str, int]


class SnapshotResponse(BaseModel):
    """Response for snapshot trigger."""
    job_id: str
    message: str


# --- Helper Functions ---

def get_recovery_manager(request: Request) -> RecoveryManager:
    """Get the RecoveryManager from app state."""
    if not hasattr(request.app.state, "recovery_manager"):
        raise HTTPException(status_code=503, detail="Recovery manager not initialized")
    return request.app.state.recovery_manager


# --- API Endpoints ---

@router.post("/start", response_model=RecoveryStartResponse)
async def start_recovery(
    request: Request,
    body: RecoveryStartRequest,
) -> RecoveryStartResponse:
    """Start a new recovery job.
    
    Args:
        body: Recovery configuration with mode ('leader' or 'node')
        
    Returns:
        Job ID and confirmation message
    """
    manager = get_recovery_manager(request)
    
    # Validate mode
    try:
        mode = RecoveryMode(body.mode.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode: {body.mode}. Must be 'leader' or 'node'"
        )
    
    try:
        job_id = await manager.start_recovery(mode)
        return RecoveryStartResponse(
            job_id=job_id,
            mode=mode.value,
            message=f"Recovery started in {mode.value} mode"
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/status/{job_id}", response_model=RecoveryStatusResponse)
async def get_recovery_status(
    request: Request,
    job_id: str,
) -> RecoveryStatusResponse:
    """Get the status of a recovery job.
    
    Args:
        job_id: The unique identifier of the recovery job
        
    Returns:
        Full status including progress metrics
    """
    manager = get_recovery_manager(request)
    job = manager.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    
    progress = job.progress
    return RecoveryStatusResponse(
        job_id=job.job_id,
        is_running=job.is_running,
        progress=RecoveryProgressResponse(
            state=progress.state.value,
            mode=progress.mode.value,
            ops_fetched=progress.ops_fetched,
            ops_merged=progress.ops_merged,
            ops_applied=progress.ops_applied,
            ops_remaining=progress.ops_remaining,
            ops_skipped=progress.ops_skipped,
            ops_conflicted=progress.ops_conflicted,
            peers_contacted=progress.peers_contacted,
            peers_failed=progress.peers_failed,
            start_time=progress.start_time.isoformat() if progress.start_time else None,
            end_time=progress.end_time.isoformat() if progress.end_time else None,
            last_error=progress.last_error,
            local_lamport_start=progress.local_lamport_start,
            local_lamport_end=progress.local_lamport_end,
        )
    )


@router.get("/logs/{job_id}")
async def stream_recovery_logs(
    request: Request,
    job_id: str,
    stream: bool = Query(default=False, description="Enable SSE streaming"),
) -> Any:
    """Get or stream logs for a recovery job.
    
    Args:
        job_id: The unique identifier of the recovery job
        stream: If True, returns Server-Sent Events stream
        
    Returns:
        List of log entries or SSE stream
    """
    manager = get_recovery_manager(request)
    job = manager.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    
    if not stream:
        return {"job_id": job_id, "logs": job.logs}
    
    # SSE streaming for live logs
    async def log_generator():
        last_index = 0
        while True:
            current_job = manager.get_job(job_id)
            if not current_job:
                break
            
            # Send new logs
            new_logs = current_job.logs[last_index:]
            for log in new_logs:
                yield f"data: {log}\n\n"
            last_index = len(current_job.logs)
            
            # Check if job is done
            if not current_job.is_running:
                yield f"data: [END] Job completed with state: {current_job.progress.state.value}\n\n"
                break
            
            await asyncio.sleep(0.5)
    
    return StreamingResponse(
        log_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.get("/health", response_model=NodeHealthResponse)
async def get_node_health(request: Request) -> NodeHealthResponse:
    """Get health status of this node and its peers.
    
    Returns:
        Node health information including peer status
    """
    manager = get_recovery_manager(request)
    health = await manager.get_node_health()
    
    return NodeHealthResponse(
        node=health["node"],
        state=health["state"],
        is_ready=health["is_ready"],
        local_stats=health["local_stats"],
        peers=health["peers"],
    )


@router.get("/gap", response_model=SyncGapResponse)
async def get_sync_gap(request: Request) -> SyncGapResponse:
    """Get the sync gap between this node and peers.
    
    Returns:
        Local lamport and gaps to each peer
    """
    manager = get_recovery_manager(request)
    gaps = await manager.get_sync_gap()
    
    local_max = gaps.pop("local_max_lamport", 0)
    return SyncGapResponse(
        local_max_lamport=local_max,
        gaps=gaps,
    )


@router.post("/snapshot", response_model=SnapshotResponse)
async def force_snapshot(request: Request) -> SnapshotResponse:
    """Force a snapshot/full resync from peers.
    
    This triggers a full recovery process to ensure
    the node is fully synchronized.
    
    Returns:
        Job ID for the snapshot operation
    """
    manager = get_recovery_manager(request)
    
    try:
        result = await manager.force_snapshot()
        return SnapshotResponse(
            job_id=result["job_id"],
            message=result["message"],
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/jobs")
async def list_recovery_jobs(request: Request) -> Dict[str, Any]:
    """List all recovery jobs.
    
    Returns:
        Dictionary of all jobs with their status
    """
    manager = get_recovery_manager(request)
    jobs = manager.get_all_jobs()
    
    return {
        "jobs": [
            {
                "job_id": job.job_id,
                "mode": job.mode.value,
                "state": job.progress.state.value,
                "is_running": job.is_running,
                "start_time": job.progress.start_time.isoformat() if job.progress.start_time else None,
                "end_time": job.progress.end_time.isoformat() if job.progress.end_time else None,
            }
            for job in jobs.values()
        ]
    }


@router.get("/state")
async def get_recovery_state(request: Request) -> Dict[str, Any]:
    """Get the current recovery state of the node.
    
    Returns:
        Current state machine state and readiness
    """
    manager = get_recovery_manager(request)
    
    return {
        "state": manager.state.value,
        "is_ready": manager.is_ready,
        "is_syncing": manager.is_syncing,
        "node": manager.settings.node_name,
    }


# --- Dashboard Endpoint ---

@router.get("/dashboard", response_class=HTMLResponse)
async def recovery_dashboard(request: Request) -> HTMLResponse:
    """Serve the recovery dashboard HTML page."""
    
    # Get the base URL for API calls
    base_url = str(request.base_url).rstrip("/")
    
    dashboard_html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Recovery Dashboard - Distributed Database</title>
    <style>
        :root {{
            --bg-primary: #1a1a2e;
            --bg-secondary: #16213e;
            --bg-card: #0f3460;
            --text-primary: #eee;
            --text-secondary: #aaa;
            --accent-green: #00d09c;
            --accent-red: #ff6b6b;
            --accent-yellow: #feca57;
            --accent-blue: #54a0ff;
        }}
        
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        
        header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        
        header h1 {{
            font-size: 2em;
            margin-bottom: 10px;
        }}
        
        header .subtitle {{
            color: var(--text-secondary);
        }}
        
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        
        .card {{
            background: var(--bg-card);
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        }}
        
        .card h2 {{
            font-size: 1.2em;
            margin-bottom: 15px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .card h2 .icon {{
            font-size: 1.5em;
        }}
        
        .status-indicator {{
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
        }}
        
        .status-healthy {{ background: var(--accent-green); }}
        .status-syncing {{ background: var(--accent-yellow); animation: pulse 1s infinite; }}
        .status-error {{ background: var(--accent-red); }}
        .status-unknown {{ background: var(--text-secondary); }}
        
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.5; }}
        }}
        
        .node-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
        }}
        
        .node-item {{
            background: var(--bg-secondary);
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }}
        
        .node-item .name {{
            font-weight: bold;
            margin-bottom: 5px;
        }}
        
        .node-item .status {{
            font-size: 0.9em;
            color: var(--text-secondary);
        }}
        
        .btn {{
            padding: 12px 24px;
            border: none;
            border-radius: 8px;
            font-size: 1em;
            cursor: pointer;
            transition: transform 0.1s, box-shadow 0.1s;
            font-weight: bold;
        }}
        
        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        }}
        
        .btn:active {{
            transform: translateY(0);
        }}
        
        .btn-primary {{
            background: var(--accent-blue);
            color: white;
        }}
        
        .btn-success {{
            background: var(--accent-green);
            color: white;
        }}
        
        .btn-warning {{
            background: var(--accent-yellow);
            color: #333;
        }}
        
        .btn-danger {{
            background: var(--accent-red);
            color: white;
        }}
        
        .btn:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }}
        
        .button-group {{
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }}
        
        .progress-container {{
            margin: 15px 0;
        }}
        
        .progress-bar {{
            height: 24px;
            background: var(--bg-secondary);
            border-radius: 12px;
            overflow: hidden;
            position: relative;
        }}
        
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, var(--accent-blue), var(--accent-green));
            border-radius: 12px;
            transition: width 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
            font-size: 0.85em;
        }}
        
        .progress-label {{
            display: flex;
            justify-content: space-between;
            font-size: 0.9em;
            color: var(--text-secondary);
            margin-top: 5px;
        }}
        
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
        }}
        
        .metric-item {{
            background: var(--bg-secondary);
            padding: 12px;
            border-radius: 8px;
        }}
        
        .metric-item .label {{
            font-size: 0.85em;
            color: var(--text-secondary);
            margin-bottom: 4px;
        }}
        
        .metric-item .value {{
            font-size: 1.4em;
            font-weight: bold;
        }}
        
        .log-container {{
            background: #0a0a15;
            border-radius: 8px;
            padding: 15px;
            height: 300px;
            overflow-y: auto;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 0.85em;
        }}
        
        .log-entry {{
            padding: 4px 0;
            border-bottom: 1px solid #222;
        }}
        
        .log-entry:last-child {{
            border-bottom: none;
        }}
        
        .log-entry.error {{
            color: var(--accent-red);
        }}
        
        .log-entry.warning {{
            color: var(--accent-yellow);
        }}
        
        .log-entry.success {{
            color: var(--accent-green);
        }}
        
        .mode-select {{
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
        }}
        
        .mode-option {{
            flex: 1;
            padding: 15px;
            background: var(--bg-secondary);
            border: 2px solid transparent;
            border-radius: 8px;
            cursor: pointer;
            text-align: center;
            transition: border-color 0.2s;
        }}
        
        .mode-option:hover {{
            border-color: var(--accent-blue);
        }}
        
        .mode-option.selected {{
            border-color: var(--accent-green);
            background: rgba(0, 208, 156, 0.1);
        }}
        
        .mode-option .title {{
            font-weight: bold;
            margin-bottom: 5px;
        }}
        
        .mode-option .desc {{
            font-size: 0.85em;
            color: var(--text-secondary);
        }}
        
        .state-badge {{
            display: inline-block;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 0.9em;
            font-weight: bold;
            text-transform: uppercase;
        }}
        
        .state-ready {{ background: var(--accent-green); color: #fff; }}
        .state-syncing {{ background: var(--accent-yellow); color: #333; }}
        .state-needs_rebuild {{ background: var(--accent-blue); color: #fff; }}
        .state-startup {{ background: var(--text-secondary); color: #fff; }}
        .state-failed {{ background: var(--accent-red); color: #fff; }}
        
        .refresh-indicator {{
            font-size: 0.8em;
            color: var(--text-secondary);
            text-align: right;
            margin-top: 10px;
        }}
        
        @media (max-width: 768px) {{
            .node-grid {{
                grid-template-columns: 1fr;
            }}
            .metrics-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🔄 Recovery Dashboard</h1>
            <p class="subtitle">Distributed Database Recovery Subsystem</p>
        </header>
        
        <div class="grid">
            <!-- Node Health Card -->
            <div class="card">
                <h2><span class="icon">🖥️</span> Node Health</h2>
                <div id="nodeHealth">
                    <div class="node-grid" id="nodeGrid">
                        <div class="node-item">
                            <div class="name">Loading...</div>
                            <div class="status">Checking...</div>
                        </div>
                    </div>
                </div>
                <div class="refresh-indicator">Auto-refresh: <span id="refreshCountdown">5</span>s</div>
            </div>
            
            <!-- Current State Card -->
            <div class="card">
                <h2><span class="icon">📊</span> Current State</h2>
                <div style="text-align: center; margin: 20px 0;">
                    <span class="state-badge state-startup" id="currentState">STARTUP</span>
                </div>
                <div class="metrics-grid" id="localStats">
                    <div class="metric-item">
                        <div class="label">Max Lamport</div>
                        <div class="value" id="maxLamport">-</div>
                    </div>
                    <div class="metric-item">
                        <div class="label">Total Ops</div>
                        <div class="value" id="totalOps">-</div>
                    </div>
                    <div class="metric-item">
                        <div class="label">Unapplied</div>
                        <div class="value" id="unappliedOps">-</div>
                    </div>
                    <div class="metric-item">
                        <div class="label">Total Orders</div>
                        <div class="value" id="totalOrders">-</div>
                    </div>
                </div>
            </div>
            
            <!-- Recovery Controls Card -->
            <div class="card">
                <h2><span class="icon">🚀</span> Recovery Controls</h2>
                <div class="mode-select">
                    <div class="mode-option selected" id="modeLeader" onclick="selectMode('leader')">
                        <div class="title">Leader Recovery</div>
                        <div class="desc">Sync Node0 from replicas</div>
                    </div>
                    <div class="mode-option" id="modeNode" onclick="selectMode('node')">
                        <div class="title">Node Recovery</div>
                        <div class="desc">Replica promotion sync</div>
                    </div>
                </div>
                <div class="button-group">
                    <button class="btn btn-primary" id="btnStartRecovery" onclick="startRecovery()">
                        ▶️ Start Recovery
                    </button>
                    <button class="btn btn-warning" onclick="forceSnapshot()">
                        📸 Force Snapshot
                    </button>
                </div>
            </div>
        </div>
        
        <!-- Progress Card -->
        <div class="card" id="progressCard" style="display: none;">
            <h2><span class="icon">⏳</span> Recovery Progress</h2>
            <div class="progress-container">
                <div class="progress-bar">
                    <div class="progress-fill" id="progressFill" style="width: 0%;">0%</div>
                </div>
                <div class="progress-label">
                    <span id="progressApplied">0 ops applied</span>
                    <span id="progressRemaining">0 remaining</span>
                </div>
            </div>
            <div class="metrics-grid">
                <div class="metric-item">
                    <div class="label">Ops Fetched</div>
                    <div class="value" id="opsFetched">0</div>
                </div>
                <div class="metric-item">
                    <div class="label">Ops Merged</div>
                    <div class="value" id="opsMerged">0</div>
                </div>
                <div class="metric-item">
                    <div class="label">Conflicts Resolved</div>
                    <div class="value" id="opsConflicted">0</div>
                </div>
                <div class="metric-item">
                    <div class="label">Ops Skipped</div>
                    <div class="value" id="opsSkipped">0</div>
                </div>
            </div>
        </div>
        
        <!-- Logs Card -->
        <div class="card">
            <h2><span class="icon">📜</span> Recovery Logs</h2>
            <div class="log-container" id="logContainer">
                <div class="log-entry">Waiting for recovery job...</div>
            </div>
        </div>
    </div>
    
    <script>
        const API_BASE = '';  // Same origin
        let selectedMode = 'leader';
        let currentJobId = null;
        let refreshInterval = null;
        let logEventSource = null;
        
        // Mode selection
        function selectMode(mode) {{
            selectedMode = mode;
            document.getElementById('modeLeader').classList.toggle('selected', mode === 'leader');
            document.getElementById('modeNode').classList.toggle('selected', mode === 'node');
        }}
        
        // Start recovery
        async function startRecovery() {{
            const btn = document.getElementById('btnStartRecovery');
            btn.disabled = true;
            btn.textContent = '⏳ Starting...';
            
            try {{
                const response = await fetch(API_BASE + '/recovery/start', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ mode: selectedMode }})
                }});
                
                if (!response.ok) {{
                    const error = await response.json();
                    throw new Error(error.detail || 'Failed to start recovery');
                }}
                
                const data = await response.json();
                currentJobId = data.job_id;
                addLog(`Recovery started: ${{data.message}} (Job: ${{data.job_id}})`, 'success');
                
                // Show progress card
                document.getElementById('progressCard').style.display = 'block';
                
                // Start polling status
                startStatusPolling();
                
                // Start log streaming
                startLogStreaming();
                
            }} catch (error) {{
                addLog(`Error: ${{error.message}}`, 'error');
            }} finally {{
                btn.disabled = false;
                btn.textContent = '▶️ Start Recovery';
            }}
        }}
        
        // Force snapshot
        async function forceSnapshot() {{
            try {{
                const response = await fetch(API_BASE + '/recovery/snapshot', {{
                    method: 'POST'
                }});
                
                if (!response.ok) {{
                    const error = await response.json();
                    throw new Error(error.detail || 'Failed to start snapshot');
                }}
                
                const data = await response.json();
                currentJobId = data.job_id;
                addLog(`Snapshot initiated: ${{data.message}} (Job: ${{data.job_id}})`, 'success');
                
                document.getElementById('progressCard').style.display = 'block';
                startStatusPolling();
                startLogStreaming();
                
            }} catch (error) {{
                addLog(`Error: ${{error.message}}`, 'error');
            }}
        }}
        
        // Poll health status
        async function fetchHealth() {{
            try {{
                const response = await fetch(API_BASE + '/recovery/health');
                const data = await response.json();
                
                // Update state badge
                const stateBadge = document.getElementById('currentState');
                stateBadge.textContent = data.state.toUpperCase();
                stateBadge.className = 'state-badge state-' + data.state;
                
                // Update local stats
                const stats = data.local_stats;
                document.getElementById('maxLamport').textContent = stats.max_lamport;
                document.getElementById('totalOps').textContent = stats.total_ops;
                document.getElementById('unappliedOps').textContent = stats.unapplied_ops;
                document.getElementById('totalOrders').textContent = stats.total_orders;
                
                // Update node grid
                const nodeGrid = document.getElementById('nodeGrid');
                let html = `
                    <div class="node-item">
                        <span class="status-indicator ${{data.is_ready ? 'status-healthy' : 'status-syncing'}}"></span>
                        <div class="name">${{data.node}} (This)</div>
                        <div class="status">${{data.state}}</div>
                    </div>
                `;
                
                for (const peer of data.peers) {{
                    const statusClass = peer.status === 'healthy' ? 'status-healthy' : 'status-error';
                    html += `
                        <div class="node-item">
                            <span class="status-indicator ${{statusClass}}"></span>
                            <div class="name">${{peer.name}}</div>
                            <div class="status">${{peer.status}}${{peer.promoted ? ' (promoted)' : ''}}</div>
                        </div>
                    `;
                }}
                
                nodeGrid.innerHTML = html;
                
            }} catch (error) {{
                console.error('Failed to fetch health:', error);
            }}
        }}
        
        // Poll job status
        async function fetchJobStatus() {{
            if (!currentJobId) return;
            
            try {{
                const response = await fetch(API_BASE + '/recovery/status/' + currentJobId);
                if (!response.ok) return;
                
                const data = await response.json();
                const progress = data.progress;
                
                // Update progress bar
                const total = progress.ops_merged || progress.ops_fetched || 1;
                const applied = progress.ops_applied;
                const percentage = Math.round((applied / total) * 100);
                
                const progressFill = document.getElementById('progressFill');
                progressFill.style.width = percentage + '%';
                progressFill.textContent = percentage + '%';
                
                document.getElementById('progressApplied').textContent = applied + ' ops applied';
                document.getElementById('progressRemaining').textContent = progress.ops_remaining + ' remaining';
                
                // Update metrics
                document.getElementById('opsFetched').textContent = progress.ops_fetched;
                document.getElementById('opsMerged').textContent = progress.ops_merged;
                document.getElementById('opsConflicted').textContent = progress.ops_conflicted;
                document.getElementById('opsSkipped').textContent = progress.ops_skipped;
                
                // Check if done
                if (!data.is_running) {{
                    if (progress.state === 'ready') {{
                        addLog('Recovery completed successfully!', 'success');
                    }} else if (progress.state === 'failed') {{
                        addLog('Recovery failed: ' + progress.last_error, 'error');
                    }}
                    stopStatusPolling();
                }}
                
            }} catch (error) {{
                console.error('Failed to fetch job status:', error);
            }}
        }}
        
        // Start status polling
        function startStatusPolling() {{
            if (refreshInterval) clearInterval(refreshInterval);
            refreshInterval = setInterval(fetchJobStatus, 1000);
        }}
        
        // Stop status polling
        function stopStatusPolling() {{
            if (refreshInterval) {{
                clearInterval(refreshInterval);
                refreshInterval = null;
            }}
        }}
        
        // Start log streaming
        function startLogStreaming() {{
            if (logEventSource) {{
                logEventSource.close();
            }}
            
            if (!currentJobId) return;
            
            logEventSource = new EventSource(API_BASE + '/recovery/logs/' + currentJobId + '?stream=true');
            
            logEventSource.onmessage = function(event) {{
                const logContainer = document.getElementById('logContainer');
                const entry = document.createElement('div');
                entry.className = 'log-entry';
                
                const text = event.data;
                if (text.includes('ERROR') || text.includes('FAIL')) {{
                    entry.classList.add('error');
                }} else if (text.includes('WARNING')) {{
                    entry.classList.add('warning');
                }} else if (text.includes('[END]') || text.includes('complete')) {{
                    entry.classList.add('success');
                }}
                
                entry.textContent = text;
                logContainer.appendChild(entry);
                logContainer.scrollTop = logContainer.scrollHeight;
            }};
            
            logEventSource.onerror = function() {{
                logEventSource.close();
                logEventSource = null;
            }};
        }}
        
        // Add log entry manually
        function addLog(message, type) {{
            const logContainer = document.getElementById('logContainer');
            const entry = document.createElement('div');
            entry.className = 'log-entry ' + (type || '');
            entry.textContent = '[' + new Date().toISOString() + '] ' + message;
            logContainer.appendChild(entry);
            logContainer.scrollTop = logContainer.scrollHeight;
        }}
        
        // Countdown timer for auto-refresh
        let countdown = 5;
        function updateCountdown() {{
            countdown--;
            if (countdown <= 0) {{
                countdown = 5;
                fetchHealth();
            }}
            document.getElementById('refreshCountdown').textContent = countdown;
        }}
        
        // Initialize
        fetchHealth();
        setInterval(updateCountdown, 1000);
    </script>
</body>
</html>'''
    
    return HTMLResponse(content=dashboard_html)
