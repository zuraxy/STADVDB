"""HTTP endpoints for the transaction orchestrator."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import asyncpg
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from ..db import get_pool
from ..config import get_settings
from ..utils import lamport as lamport_utils
from ..orchestrator import (
    IsolationLevel,
    OrchestrationInput,
    ScenarioType,
    TransactionActorInput,
)

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


class TransactionActorModel(BaseModel):
    name: str = Field(default="tx_a", min_length=1, max_length=32)
    node: str = Field(default="node0")
    isolation_level: IsolationLevel = IsolationLevel.READ_COMMITTED
    delay_seconds: float = Field(default=0.0, ge=0.0, le=30.0)
    new_quantity: Optional[int] = None
    auto_increment: bool = False  # If True, increment quantity by 1 instead of setting

    def to_input(self) -> TransactionActorInput:
        return TransactionActorInput(
            name=self.name.strip() or "actor",
            node=self.node.lower(),
            isolation_level=self.isolation_level,
            delay_seconds=self.delay_seconds,
            new_quantity=self.new_quantity,
            auto_increment=self.auto_increment,
        )


class RunOrchestrationRequest(BaseModel):
    """Request model that accepts both frontend format and explicit actors format."""
    scenario: ScenarioType
    order_id: Optional[UUID] = None
    # Explicit actors array (advanced usage)
    actors: Optional[List[TransactionActorModel]] = None
    # Frontend simplified fields
    isolation_level: Optional[IsolationLevel] = IsolationLevel.READ_COMMITTED
    parallel_clients: Optional[int] = Field(default=2, ge=2, le=16)
    node_x: Optional[str] = "node0"
    node_y: Optional[str] = "node1"
    new_value_1: Optional[int] = None
    new_value_2: Optional[int] = None

    @model_validator(mode='after')
    def validate_and_build_actors(self):
        # If actors are explicitly provided, validate them
        if self.actors is not None and len(self.actors) > 0:
            scenario = self.scenario
            expected = scenario.roles
            if len(self.actors) != len(expected):
                raise ValueError(
                    f"Scenario {scenario.value} requires exactly {len(expected)} actors"
                )
            for actor, role in zip(self.actors, expected):
                if role == "write" and actor.new_quantity is None:
                    raise ValueError(
                        f"Actor '{actor.name}' must include new_quantity for write operations"
                    )
            return self
        
        # Build actors from frontend simplified fields
        scenario = self.scenario
        isolation = self.isolation_level or IsolationLevel.READ_COMMITTED
        
        if scenario == ScenarioType.READ_READ:
            # Two readers on different nodes
            self.actors = [
                TransactionActorModel(
                    name="reader_a",
                    node=self.node_x or "node0",
                    isolation_level=isolation,
                ),
                TransactionActorModel(
                    name="reader_b",
                    node=self.node_y or "node1",
                    isolation_level=isolation,
                ),
            ]
        elif scenario == ScenarioType.READ_WRITE:
            # Writer on node_x (Master), Reader on node_y (Slave)
            # This matches the frontend labels
            write_value = self.new_value_1 if self.new_value_1 is not None else 1
            self.actors = [
                TransactionActorModel(
                    name="writer",
                    node=self.node_x or "node0",  # Writer on master (node_x)
                    isolation_level=isolation,
                    new_quantity=write_value,
                ),
                TransactionActorModel(
                    name="reader",
                    node=self.node_y or "node1",  # Reader on slave (node_y)
                    isolation_level=isolation,
                ),
            ]
        elif scenario == ScenarioType.WRITE_WRITE:
            # Two writers with auto-increment (each adds 1 to current quantity)
            # This demonstrates lost update scenarios
            self.actors = [
                TransactionActorModel(
                    name="writer_a",
                    node=self.node_x or "node0",
                    isolation_level=isolation,
                    auto_increment=True,
                ),
                TransactionActorModel(
                    name="writer_b",
                    node=self.node_y or "node1",
                    isolation_level=isolation,
                    auto_increment=True,
                ),
            ]
        
        # Validate the generated actors
        if self.actors:
            expected = scenario.roles
            for actor, role in zip(self.actors, expected):
                if role == "write" and actor.new_quantity is None and not actor.auto_increment:
                    raise ValueError(
                        f"Actor '{actor.name}' requires new_quantity or auto_increment for write operations"
                    )
        
        return self

    def to_input(self) -> OrchestrationInput:
        return OrchestrationInput(
            scenario=self.scenario,
            actors=[actor.to_input() for actor in self.actors],
            order_id=self.order_id,
        )


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def run_orchestration(request: Request, payload: RunOrchestrationRequest) -> dict:
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Orchestrator not configured")
    try:
        state = await orchestrator.start_run(payload.to_input())
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"run_id": state.id, "status": "started"}


@router.get("/status/{run_id}")
async def orchestration_status(request: Request, run_id: str) -> dict:
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Orchestrator not configured")
    status_payload = orchestrator.get_status(run_id)
    if status_payload is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Run not found")
    return status_payload


@router.get("/logs/{run_id}")
async def orchestration_logs(request: Request, run_id: str) -> dict:
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Orchestrator not configured")
    logs = orchestrator.get_logs(run_id)
    if logs is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Run not found")
    return logs


@router.post("/abort/{run_id}")
async def orchestration_abort(request: Request, run_id: str) -> dict:
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Orchestrator not configured")
    success = await orchestrator.abort_run(run_id)
    if not success:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Run not found")
    return {"run_id": run_id, "status": "aborted"}


class LocalTransactionRequest(BaseModel):
    """Request to execute a transaction actor on this node's local database."""
    order_id: UUID
    actor_id: str
    role: str  # "read" or "write"
    isolation_level: IsolationLevel = IsolationLevel.READ_COMMITTED
    delay_seconds: float = 0.0
    delay_before_commit: float = 0.0  # Delay after write but before commit (for dirty read testing)
    delay_after_lock: float = 0.0  # Delay after FOR UPDATE lock (for write-write contention)
    new_quantity: Optional[int] = None
    auto_increment: bool = False  # If True, increment quantity by 1 instead of setting


@router.post("/local-transaction")
async def execute_local_transaction(request: Request, payload: LocalTransactionRequest) -> Dict[str, Any]:
    """
    Execute a transaction on THIS node's local database.
    Called by the orchestrator on the master node to run actors on slave nodes.
    """
    pool = get_pool()
    result: Dict[str, Any] = {
        "actor_id": payload.actor_id,
        "role": payload.role,
        "status": "running",
    }
    
    conn = await pool.acquire()
    try:
        await conn.execute(
            f"BEGIN TRANSACTION ISOLATION LEVEL {payload.isolation_level.sql_clause}"
        )
        
        if payload.role == "read":
            # First read with FOR SHARE lock
            snapshot = await conn.fetchrow(
                "SELECT quantity FROM orders WHERE order_id = $1 FOR SHARE",
                payload.order_id,
            )
            qty_before = snapshot["quantity"] if snapshot else None
            
            # Optional delay for concurrency testing
            if payload.delay_seconds > 0:
                await conn.execute("SELECT pg_sleep($1)", payload.delay_seconds)
            
            # Second read to check for changes
            follow_up = await conn.fetchrow(
                "SELECT quantity FROM orders WHERE order_id = $1",
                payload.order_id,
            )
            qty_after = follow_up["quantity"] if follow_up else None
            
            await conn.execute("COMMIT")
            result["status"] = "committed"
            result["details"] = {
                "initial_quantity": qty_before,
                "final_quantity": qty_after,
            }
            
        elif payload.role == "write":
            if payload.new_quantity is None and not payload.auto_increment:
                raise ValueError("new_quantity or auto_increment required for write operations")
            
            # Get settings for origin node
            settings = get_settings()
            origin_node = settings.node_name
            
            # Lock row for update
            row = await conn.fetchrow(
                "SELECT quantity, payload FROM orders WHERE order_id = $1 FOR UPDATE",
                payload.order_id,
            )
            current_qty = row["quantity"] if row else None
            current_payload = row["payload"] if row else None
            
            # Delay after getting lock (for write-write contention testing)
            if payload.delay_after_lock > 0:
                await asyncio.sleep(payload.delay_after_lock)
            
            # Optional delay using pg_sleep
            if payload.delay_seconds > 0:
                await conn.execute("SELECT pg_sleep($1)", payload.delay_seconds)
            
            # Determine final quantity value
            if payload.auto_increment:
                final_quantity = (current_qty or 0) + 1
            else:
                final_quantity = payload.new_quantity
            
            # Perform update
            await conn.execute(
                "UPDATE orders SET quantity = $2, updated_at = NOW() WHERE order_id = $1",
                payload.order_id,
                final_quantity,
            )
            
            # Write to op_log for replication
            lamport_value = await lamport_utils.next_lamport(conn, origin_node)
            op_payload = {"quantity": final_quantity, "payload": current_payload}
            op_payload_json = json.dumps(op_payload)
            await conn.execute(
                """
                INSERT INTO op_log (
                    op_id, origin_node, op_type, table_name, row_id, payload,
                    ts, lamport, applied, applied_ts
                ) VALUES ($1,$2,$3,$4,$5,$6::jsonb,NOW(),$7,false,NULL)
                ON CONFLICT (op_id) DO NOTHING
                """,
                uuid4(),
                origin_node,
                "upsert",
                "orders",
                payload.order_id,
                op_payload_json,
                lamport_value,
            )
            
            # Delay before commit (for dirty read testing in READ_WRITE scenarios)
            if payload.delay_before_commit > 0:
                await asyncio.sleep(payload.delay_before_commit)
            
            await conn.execute("COMMIT")
            result["status"] = "committed"
            result["details"] = {
                "locked_quantity": current_qty,
                "committed_quantity": final_quantity,
            }
        else:
            raise ValueError(f"Unknown role: {payload.role}")
            
    except Exception as exc:
        await conn.execute("ROLLBACK")
        sqlstate = getattr(exc, "sqlstate", None)
        if sqlstate == "40001":
            result["status"] = "serialization_aborted"
            result["error"] = str(exc)
        else:
            result["status"] = "error"
            result["error"] = str(exc)
    finally:
        await pool.release(conn)
    
    return result


@router.get("/stream/{run_id}")
async def orchestration_stream(request: Request, run_id: str):
    """Server-Sent Events stream for real-time orchestration updates."""
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Orchestrator not configured")
    
    status_payload = orchestrator.get_status(run_id)
    if status_payload is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Run not found")

    async def event_generator():
        last_log_count = 0
        while True:
            try:
                # Get current logs
                logs_payload = orchestrator.get_logs(run_id)
                if logs_payload and "logs" in logs_payload:
                    current_logs = logs_payload["logs"]
                    # Send only new logs
                    if len(current_logs) > last_log_count:
                        for log_entry in current_logs[last_log_count:]:
                            import json
                            yield f"data: {json.dumps(log_entry)}\n\n"
                        last_log_count = len(current_logs)
                
                # Check if run is still active
                current_status = orchestrator.get_status(run_id)
                if current_status and current_status.get("status") not in ("running", "started"):
                    # Send final status and close
                    import json
                    yield f"data: {json.dumps({'event': 'finished', 'status': current_status.get('status')})}\n\n"
                    break
                
                await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break
            except Exception:
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
