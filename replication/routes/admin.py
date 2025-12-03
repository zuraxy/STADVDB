"""Administrative and health endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from ..config import get_settings
from ..db import get_pool
from ..models import PromoteToggle, DemoteToggle

router = APIRouter(tags=["admin"])

# Global node disabled flag - simulates node being "powered off"
_node_disabled: bool = False


class NodeToggleRequest(BaseModel):
	"""Request to toggle node disabled state."""
	disabled: bool


def is_node_disabled() -> bool:
	"""Check if this node is disabled (simulated power off)."""
	return _node_disabled


def set_node_disabled(disabled: bool) -> None:
	"""Set the node disabled state."""
	global _node_disabled
	_node_disabled = disabled


@router.get("/health")
async def healthcheck() -> dict:
	# Return error if node is disabled
	if _node_disabled:
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail="Node is disabled (simulated power off)"
		)
	
	pool = get_pool()
	async with pool.acquire() as conn:
		await conn.execute("SELECT 1")
	return {"status": "ok", "database": "up"}


@router.get("/admin/disabled-status")
async def get_disabled_status() -> dict:
	"""Get the disabled status of this node."""
	settings = get_settings()
	return {
		"node": settings.node_name,
		"disabled": _node_disabled,
	}


@router.post("/admin/toggle-disabled")
async def toggle_disabled(body: NodeToggleRequest) -> dict:
	"""Toggle the disabled state of this node."""
	global _node_disabled
	settings = get_settings()
	_node_disabled = body.disabled
	return {
		"node": settings.node_name,
		"disabled": _node_disabled,
		"status": "disabled" if _node_disabled else "enabled",
	}


@router.get("/status/replication")
async def replication_status(request: Request) -> dict:
	# If node is disabled, return minimal status indicating unavailable
	if _node_disabled:
		settings = get_settings()
		return {
			"node": settings.node_name,
			"disabled": True,
			"status": "disabled",
			"nodes": [{
				"name": settings.node_name,
				"role": "disabled",
				"status": "disabled",
				"error": "Node is disabled (simulated power off)",
			}],
		}
	
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
		"disabled": _node_disabled,
		"nodes": nodes,
		"replicator": replicator_metrics,
		"applier": applier_metrics,
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
	# Check if node is disabled
	if _node_disabled:
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail="This node is disabled"
		)
	
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


@router.post("/admin/node/{node_name}/toggle")
async def proxy_node_toggle(node_name: str, body: NodeToggleRequest, request: Request) -> dict:
	"""Proxy request to toggle a peer node's disabled state."""
	settings = get_settings()
	
	# If targeting this node, handle locally
	if node_name.lower() == settings.node_name.lower():
		global _node_disabled
		_node_disabled = body.disabled
		return {
			"node": settings.node_name,
			"disabled": _node_disabled,
			"status": "disabled" if _node_disabled else "enabled",
		}
	
	# Find the peer node URL
	peer_url = None
	for peer in settings.peer_nodes:
		if peer.name.lower() == node_name.lower():
			peer_url = peer.base_url
			break
	
	if not peer_url:
		raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Node {node_name} not found in peer list")
	
	# Proxy to peer node
	client = request.app.state.http_client
	try:
		result = await client.post_json(f"{peer_url}/admin/toggle-disabled", {"disabled": body.disabled})
		return result
	except Exception as e:
		raise HTTPException(
			status.HTTP_503_SERVICE_UNAVAILABLE, 
			detail=f"Failed to reach node {node_name}: {str(e)}"
		)


@router.get("/admin/node/{node_name}/disabled-status")
async def proxy_node_disabled_status(node_name: str, request: Request) -> dict:
	"""Proxy request to get a peer node's disabled status."""
	settings = get_settings()
	
	# If targeting this node, handle locally
	if node_name.lower() == settings.node_name.lower():
		return {
			"node": settings.node_name,
			"disabled": _node_disabled,
		}
	
	# Find the peer node URL
	peer_url = None
	for peer in settings.peer_nodes:
		if peer.name.lower() == node_name.lower():
			peer_url = peer.base_url
			break
	
	if not peer_url:
		raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Node {node_name} not found in peer list")
	
	# Proxy to peer node
	client = request.app.state.http_client
	try:
		result = await client.get_json(f"{peer_url}/admin/disabled-status")
		return result
	except Exception as e:
		# Node unreachable - return as unreachable
		return {
			"node": node_name,
			"disabled": False,
			"unreachable": True,
			"error": str(e),
		}
