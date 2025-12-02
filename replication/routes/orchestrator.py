"""HTTP endpoints for the transaction orchestrator."""

from __future__ import annotations

import asyncio
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

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

    def to_input(self) -> TransactionActorInput:
        return TransactionActorInput(
            name=self.name.strip() or "actor",
            node=self.node.lower(),
            isolation_level=self.isolation_level,
            delay_seconds=self.delay_seconds,
            new_quantity=self.new_quantity,
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
            # One writer, one reader
            self.actors = [
                TransactionActorModel(
                    name="writer",
                    node=self.node_x or "node0",
                    isolation_level=isolation,
                    new_quantity=self.new_value_1,
                ),
                TransactionActorModel(
                    name="reader",
                    node=self.node_y or "node1",
                    isolation_level=isolation,
                ),
            ]
        elif scenario == ScenarioType.WRITE_WRITE:
            # Two writers on same or different nodes
            self.actors = [
                TransactionActorModel(
                    name="writer_a",
                    node=self.node_x or "node0",
                    isolation_level=isolation,
                    new_quantity=self.new_value_1,
                ),
                TransactionActorModel(
                    name="writer_b",
                    node=self.node_y or "node1",
                    isolation_level=isolation,
                    new_quantity=self.new_value_2,
                ),
            ]
        
        # Validate the generated actors
        if self.actors:
            expected = scenario.roles
            for actor, role in zip(self.actors, expected):
                if role == "write" and actor.new_quantity is None:
                    raise ValueError(
                        f"Actor '{actor.name}' requires new_quantity for write operations (provide new_value_1/new_value_2)"
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
