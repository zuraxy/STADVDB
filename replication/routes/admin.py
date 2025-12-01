"""Administrative and health endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..config import get_settings
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
	settings = get_settings()
	replicator_metrics = replicator.metrics() if replicator else {}
	applier_metrics = applier.metrics() if applier else {}
	peer_errors = replicator_metrics.get("peer_errors", {}) if replicator_metrics else {}
	last_seen = replicator_metrics.get("last_seen", {}) if replicator_metrics else {}
	nodes = [
		{
			"name": settings.node_name,
			"role": "primary" if settings.node_name == settings.default_master else "replica",
			"status": "online" if not applier_metrics.get("last_error") else "degraded",
			"promoted": request.app.state.promoted,
			"url": None,
		},
	]
	for peer in settings.peer_nodes:
		if peer.name == settings.node_name:
			continue
		peer_error = peer_errors.get(peer.base_url)
		last_seen_value = last_seen.get(peer.base_url, -1)
		if peer_error:
			status_value = "error"
		elif last_seen_value < 0:
			status_value = "checking"
		else:
			status_value = "online"
		nodes.append(
			{
				"name": peer.name,
				"role": "peer",
				"url": peer.base_url,
				"status": status_value,
				"last_seen_lamport": last_seen_value,
				"error": peer_error,
			}
		)
	return {
		"node": settings.node_name,
		"default_master": settings.default_master,
		"promoted": request.app.state.promoted,
		"partition_rule": settings.partition_rule,
		"nodes": nodes,
		"replicator": replicator_metrics,
		"applier": applier_metrics,
	}


@router.post("/promote")
async def toggle_promotion(body: PromoteToggle, request: Request) -> dict:
	request.app.state.promoted = body.promote
	return {"promoted": request.app.state.promoted}
