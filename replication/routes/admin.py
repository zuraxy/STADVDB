"""Administrative and health endpoints."""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status

from ..config import get_settings
from ..db import get_pool
from ..models import PromoteToggle, DemoteToggle

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
	
	# Build node status with improved detection
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
		
		# Check HTTP client for recent errors
		http_client = getattr(request.app.state, "http_client", None)
		http_error = None
		if http_client:
			http_error = http_client.get_node_error(peer.base_url)
		
		# Determine status based on multiple signals
		if peer_error or http_error:
			status_value = "error"
			error_msg = peer_error or http_error
		elif last_seen_value < 0:
			status_value = "checking"
			error_msg = None
		else:
			status_value = "online"
			error_msg = None
			
		nodes.append(
			{
				"name": peer.name,
				"role": "peer",
				"url": peer.base_url,
				"status": status_value,
				"last_seen_lamport": last_seen_value,
				"error": error_msg,
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


@router.get("/status/nodes")
async def get_all_nodes_health(request: Request) -> dict:
	"""Get health status of all nodes with individual timeout handling.
	
	This endpoint is resilient - it returns whatever data is available
	even if some nodes are down.
	"""
	settings = get_settings()
	http_client = getattr(request.app.state, "http_client", None)
	recovery_runner = getattr(request.app.state, "recovery_test_runner", None)
	
	nodes = {}
	
	# Check if local node is simulated as unavailable
	local_simulated_unavailable = False
	if recovery_runner:
		sim_status = recovery_runner._simulated_availability.get(settings.node_name)
		if sim_status is not None and not sim_status:
			local_simulated_unavailable = True
	
	# Local node is always available (we're running) - unless simulated as down
	nodes[settings.node_name] = {
		"name": settings.node_name,
		"status": "error" if local_simulated_unavailable else "online",
		"is_local": True,
		"promoted": getattr(request.app.state, "promoted", False),
		"simulated": local_simulated_unavailable,
	}
	
	# Check each peer with individual timeout
	async def check_peer(peer):
		# Check if simulated as unavailable
		if recovery_runner:
			sim_status = recovery_runner._simulated_availability.get(peer.name)
			if sim_status is not None and not sim_status:
				return {
					"name": peer.name,
					"status": "error",
					"url": peer.base_url,
					"error": "Simulated unavailable",
					"simulated": True,
				}
		
		if not http_client:
			return {
				"name": peer.name,
				"status": "unknown",
				"error": "No HTTP client",
			}
		try:
			# Quick health check with short timeout
			result = await asyncio.wait_for(
				http_client.get_json_safe(f"{peer.base_url}/health", default=None),
				timeout=3.0
			)
			if result and result.get("status") == "ok":
				return {
					"name": peer.name,
					"status": "online",
					"url": peer.base_url,
				}
			else:
				return {
					"name": peer.name,
					"status": "error",
					"url": peer.base_url,
					"error": "Health check failed",
				}
		except asyncio.TimeoutError:
			return {
				"name": peer.name,
				"status": "error",
				"url": peer.base_url,
				"error": "Timeout",
			}
		except Exception as e:
			return {
				"name": peer.name,
				"status": "error",
				"url": peer.base_url,
				"error": str(e),
			}
	
	# Check all peers concurrently
	peer_checks = [check_peer(peer) for peer in settings.peer_nodes if peer.name != settings.node_name]
	if peer_checks:
		results = await asyncio.gather(*peer_checks, return_exceptions=True)
		for result in results:
			if isinstance(result, dict):
				nodes[result["name"]] = result
			elif isinstance(result, Exception):
				pass  # Ignore exceptions, node stays as unknown
	
	return {
		"local_node": settings.node_name,
		"nodes": nodes,
		"all_online": all(n.get("status") == "online" for n in nodes.values()),
	}


@router.post("/promote")
async def toggle_promotion(body: PromoteToggle, request: Request) -> dict:
	request.app.state.promoted = body.promote
	settings = get_settings()
	pool = get_pool()
	
	# Record promotion in promotion_log if promoting
	if body.promote:
		try:
			async with pool.acquire() as conn:
				await conn.execute("""
					CREATE TABLE IF NOT EXISTS promotion_log (
						id SERIAL PRIMARY KEY,
						node TEXT NOT NULL,
						promoted_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
						demoted_at TIMESTAMP WITH TIME ZONE
					)
				""")
				await conn.execute("""
					INSERT INTO promotion_log (node, promoted_at)
					VALUES ($1, NOW())
				""", settings.node_name)
		except Exception:
			pass  # Non-critical
	
	return {"promoted": request.app.state.promoted}


@router.post("/demote")
async def demote_node(body: DemoteToggle, request: Request) -> dict:
	"""Demote this node (clear promoted flag)."""
	if body.demote:
		request.app.state.promoted = False
		settings = get_settings()
		pool = get_pool()
		
		# Update promotion_log
		try:
			async with pool.acquire() as conn:
				await conn.execute("""
					UPDATE promotion_log 
					SET demoted_at = NOW() 
					WHERE node = $1 AND demoted_at IS NULL
				""", settings.node_name)
		except Exception:
			pass  # Table may not exist
		
		return {"node": settings.node_name, "promoted": False, "status": "demoted"}
	
	return {"promoted": request.app.state.promoted}


@router.get("/proxy/node/{node_name}/orders")
async def proxy_node_orders(node_name: str, request: Request) -> list:
	"""Proxy request to get local orders from a specific peer node"""
	settings = get_settings()
	
	# Find the peer node URL
	peer_url = None
	for peer in settings.peer_nodes:
		if peer.name.lower() == node_name.lower():
			peer_url = peer.base_url
			break
	
	if not peer_url:
		raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Node {node_name} not found in peer list")
	
	# Fetch from peer's local endpoint
	client = request.app.state.http_client
	try:
		orders = await client.get_json(f"{peer_url}/orders/local/all")
		return orders
	except Exception as e:
		raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Failed to reach node {node_name}: {str(e)}")
