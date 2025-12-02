"""HTTP endpoints for the parameterized transaction orchestrator."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, validator

from ..orchestrator import IsolationLevel, OrchestrationParameters, ScenarioKind

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


class RunOrchestrationRequest(BaseModel):
    """Request payload used to launch a new orchestration run."""

    scenario: ScenarioKind = ScenarioKind.READ_READ
    isolation_level: IsolationLevel = IsolationLevel.READ_COMMITTED
    parallel_clients: int = Field(default=2, ge=2, le=16)
    order_id: Optional[str] = Field(default=None)
    new_value_1: Optional[int] = Field(default=None)
    new_value_2: Optional[int] = Field(default=None)
    node_x: str = Field(default="node0", pattern=r"^node[0-2]$")  # pydantic v2: use pattern instead of regex
    node_y: str = Field(default="node1", pattern=r"^node[0-2]$")  # pydantic v2: use pattern instead of regex

    @validator("order_id")
    def _blank_to_none(cls, value: Optional[str]) -> Optional[str]:  # noqa: N805
        if value and not value.strip():
            return None
        return value

    def to_parameters(self) -> OrchestrationParameters:
        order_uuid = None
        if self.order_id:
            try:
                order_uuid = UUID(self.order_id)
            except ValueError as exc:  # pragma: no cover - validation guard
                raise ValueError("order_id must be a valid UUID") from exc
        return OrchestrationParameters(
            scenario=self.scenario,
            isolation_level=self.isolation_level,
            parallel_clients=self.parallel_clients,
            order_id=order_uuid,
            node_x=self.node_x.lower(),
            node_y=self.node_y.lower(),
            new_value_1=self.new_value_1,
            new_value_2=self.new_value_2,
        )


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def run_orchestration(request: Request, payload: RunOrchestrationRequest) -> dict:
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Orchestrator not configured")
    try:
        state = await orchestrator.start_run(payload.to_parameters())
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


@router.get("/stream/{run_id}")
async def orchestration_stream(request: Request, run_id: str) -> StreamingResponse:
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Orchestrator not configured")
    generator = await orchestrator.stream_logs(run_id)
    if generator is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Run not found")
    return StreamingResponse(generator, media_type="text/event-stream")


@router.post("/abort/{run_id}")
async def orchestration_abort(request: Request, run_id: str) -> dict:
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Orchestrator not configured")
    success = await orchestrator.abort_run(run_id)
    if not success:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Run not found")
    return {"run_id": run_id, "status": "aborted"}
