"""HTTP endpoints for the transaction orchestrator."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator

from ..orchestrator import (
    IsolationLevel,
    OrchestrationInput,
    ScenarioType,
    TransactionActorInput,
)

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


class TransactionActorModel(BaseModel):
    """Pydantic model for a single transaction actor."""
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
    """Request model for starting an orchestration run."""
    scenario: ScenarioType
    order_id: Optional[UUID] = None
    actors: List[TransactionActorModel]

    @model_validator(mode="after")
    def validate_actors(self):
        scenario = self.scenario
        actors = self.actors or []
        if scenario is None:
            return self
        expected = scenario.roles
        if len(actors) != len(expected):
            raise ValueError(
                f"Scenario {scenario.value} requires exactly {len(expected)} actors"
            )
        for actor, role in zip(actors, expected):
            if role == "write" and actor.new_quantity is None:
                raise ValueError(
                    f"Actor '{actor.name}' must include new_quantity for write operations"
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
    """Start a new orchestration run with the specified scenario and actors."""
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
    """Get the current status of an orchestration run."""
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Orchestrator not configured")
    status_payload = orchestrator.get_status(run_id)
    if status_payload is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Run not found")
    return status_payload


@router.get("/logs/{run_id}")
async def orchestration_logs(request: Request, run_id: str) -> dict:
    """Get the event logs for an orchestration run."""
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Orchestrator not configured")
    logs = orchestrator.get_logs(run_id)
    if logs is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Run not found")
    return logs


@router.post("/abort/{run_id}")
async def orchestration_abort(request: Request, run_id: str) -> dict:
    """Abort an in-progress orchestration run."""
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Orchestrator not configured")
    success = await orchestrator.abort_run(run_id)
    if not success:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Run not found")
    return {"run_id": run_id, "status": "aborted"}
