"""Administrative and health endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..db import get_pool
from ..models import PromoteToggle

router = APIRouter(tags=["admin"])


@router.get("/health")
async def healthcheck() -> dict:
	pool = get_pool()
	async with pool.acquire() as conn:
		await conn.execute("SELECT 1")
	return {"status": "ok", "database": "up"}


@router.get("/status/replication")
async def replication_status(request: Request) -> dict:
	replicator = getattr(request.app.state, "replicator", None)
	applier = getattr(request.app.state, "applier", None)
	return {
		"promoted": request.app.state.promoted,
		"replicator": replicator.metrics() if replicator else {},
		"applier": applier.metrics() if applier else {},
	}


@router.post("/promote")
async def toggle_promotion(body: PromoteToggle, request: Request) -> dict:
	request.app.state.promoted = body.promote
	return {"promoted": request.app.state.promoted}
