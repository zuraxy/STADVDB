"""API routes for recovery test suite."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from typing import Dict, List, Optional, Any

from ..recovery_tests import RecoveryTestRunner, RecoveryTestCase

router = APIRouter(prefix="/recovery-tests", tags=["recovery-tests"])


class RunTestRequest(BaseModel):
    test_case: str  # "case_1", "case_2", "case_3", "case_4"


class NodeAvailabilityRequest(BaseModel):
    node: str
    available: bool


@router.post("/run")
async def run_recovery_test(body: RunTestRequest, request: Request) -> Dict[str, Any]:
    """Run a specific recovery test case."""
    runner: Optional[RecoveryTestRunner] = getattr(request.app.state, "recovery_test_runner", None)
    
    if not runner:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Recovery test runner not initialized"
        )
    
    # Map string to enum
    case_map = {
        "case_1": RecoveryTestCase.CASE_1_REPLICATION_TO_NODE0_FAILS,
        "case_2": RecoveryTestCase.CASE_2_NODE0_RECOVERS,
        "case_3": RecoveryTestCase.CASE_3_REPLICATION_FROM_NODE0_FAILS,
        "case_4": RecoveryTestCase.CASE_4_PARTITION_NODE_RECOVERS,
    }
    
    test_case = case_map.get(body.test_case.lower())
    if not test_case:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid test case: {body.test_case}. Valid options: case_1, case_2, case_3, case_4"
        )
    
    result = await runner.run_test(test_case)
    return result.to_dict()


@router.get("/current")
async def get_current_test(request: Request) -> Dict[str, Any]:
    """Get the currently running test."""
    runner: Optional[RecoveryTestRunner] = getattr(request.app.state, "recovery_test_runner", None)
    
    if not runner:
        return {"current_test": None}
    
    current = runner.get_current_test()
    return {"current_test": current}


@router.get("/history")
async def get_test_history(request: Request) -> Dict[str, Any]:
    """Get history of all test runs."""
    runner: Optional[RecoveryTestRunner] = getattr(request.app.state, "recovery_test_runner", None)
    
    if not runner:
        return {"history": []}
    
    return {"history": runner.get_test_history()}


@router.post("/history/clear")
async def clear_test_history(request: Request) -> Dict[str, str]:
    """Clear test history."""
    runner: Optional[RecoveryTestRunner] = getattr(request.app.state, "recovery_test_runner", None)
    
    if runner:
        runner.clear_history()
    
    return {"status": "cleared"}


@router.get("/node-availability")
async def get_node_availability(request: Request) -> Dict[str, Any]:
    """Get simulated node availability states."""
    runner: Optional[RecoveryTestRunner] = getattr(request.app.state, "recovery_test_runner", None)
    
    if not runner:
        return {"availability": {"node0": True, "node1": True, "node2": True}}
    
    return {"availability": runner.get_node_availability()}


@router.post("/node-availability")
async def set_node_availability(body: NodeAvailabilityRequest, request: Request) -> Dict[str, Any]:
    """Set simulated node availability (for testing)."""
    runner: Optional[RecoveryTestRunner] = getattr(request.app.state, "recovery_test_runner", None)
    
    if not runner:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Recovery test runner not initialized"
        )
    
    runner.set_node_availability(body.node, body.available)
    
    return {
        "status": "updated",
        "node": body.node,
        "available": body.available,
        "all_availability": runner.get_node_availability(),
    }


@router.get("/cases")
async def list_test_cases() -> Dict[str, Any]:
    """List all available test cases with descriptions."""
    return {
        "cases": [
            {
                "id": "case_1",
                "name": "Replication fails from Node2/3 → Node0",
                "description": "Tests error logging and queued retry when Node0 cannot receive replication from partition nodes.",
            },
            {
                "id": "case_2",
                "name": "Node0 comes back online after missing writes",
                "description": "Tests that Node0 pulls missing oplog entries and fully resyncs after recovery.",
            },
            {
                "id": "case_3",
                "name": "Replication fails from Node0 → Node2/3",
                "description": "Tests logged failure and queued retry when partition nodes reject writes from Node0.",
            },
            {
                "id": "case_4",
                "name": "Node2/3 recovers after missing writes",
                "description": "Tests that partition nodes pull missing entries in correct order with no duplication.",
            },
        ]
    }
