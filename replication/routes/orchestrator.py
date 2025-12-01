"""HTTP endpoints for the transaction orchestrator."""

from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..orchestrator import CustomClientScript, IsolationLevel, OrchestrationInput, StatementPlan

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


class CustomStatementModel(BaseModel):
    sql: str
    params: List[Any] = Field(default_factory=list)
    delay_after: Optional[float] = Field(default=None, ge=0)
    description: Optional[str] = None

    def to_plan(self) -> StatementPlan:
        return StatementPlan(
            sql=self.sql,
            params=tuple(self.params),
            delay_after=self.delay_after or 0.0,
            description=self.description,
        )


class CustomClientModel(BaseModel):
    node: str = Field(default="node0")
    statements: List[CustomStatementModel]

    def to_script(self) -> CustomClientScript:
        return CustomClientScript(
            node=self.node.lower(),
            statements=[stmt.to_plan() for stmt in self.statements],
        )


class RunOrchestrationRequest(BaseModel):
    scenario: str = Field(
        pattern="^(Case1_readers_only|Case2_writer_readers|Case3_concurrent_writers|custom)$"
    )
    isolation_level: IsolationLevel = IsolationLevel.READ_COMMITTED
    parallel_clients: int = Field(default=2, ge=1, le=16)
    custom_transactions: Optional[List[CustomClientModel]] = None

    def to_input(self) -> OrchestrationInput:
        custom = None
        if self.scenario == "custom":
            if not self.custom_transactions:
                raise ValueError("Custom scenario requires custom_transactions payload")
            custom = [client.to_script() for client in self.custom_transactions]
        return OrchestrationInput(
            scenario=self.scenario,
            isolation_level=self.isolation_level,
            parallel_clients=self.parallel_clients,
            custom_transactions=custom,
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
