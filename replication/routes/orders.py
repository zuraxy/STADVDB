"""Order CRUD endpoints with leader-aware routing and node availability checks.

This module now supports:
1. Leader-aware routing: All writes go to current cluster leader (not hardcoded node0)
2. Node availability checks: Requests rejected with 503 if node is simulated as down
3. Full integration with ClusterManager for dynamic routing
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from .. import crud
from ..config import Settings, get_settings
from ..db import get_pool
from ..models import OrderCreate, OrderRead, OrderUpdate
from ..utils.partition import can_accept_partition, target_node_for_quantity

router = APIRouter(tags=["orders"])


# ---------------------------------------------------------------------------
# Cluster Manager Reference (injected from main.py)
# ---------------------------------------------------------------------------
_cluster_manager = None


def set_cluster_manager(cm):
	"""Inject cluster manager reference from main.py startup."""
	global _cluster_manager
	_cluster_manager = cm


def get_cluster_manager():
	"""Get the cluster manager reference."""
	return _cluster_manager


# ---------------------------------------------------------------------------
# Helpers for Leader-Aware Routing
# ---------------------------------------------------------------------------

def _check_node_available(settings: Settings):
	"""Check if this node is simulated as down. Raise 503 if so."""
	if _cluster_manager is None:
		return  # No cluster manager, allow all requests
	
	node_name = settings.node_name.lower()
	if _cluster_manager.is_node_simulated_down(node_name):
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail=f"Node {node_name} is simulated as offline - request rejected"
		)


def _is_leader(settings: Settings) -> bool:
	"""Return True if the current node is the cluster leader."""
	if _cluster_manager is None:
		# Fallback to config-based check (old behavior)
		return settings.node_name.lower() == settings.default_master.lower()
	
	current_leader = _cluster_manager.current_leader
	if current_leader:
		return settings.node_name.lower() == current_leader.lower()
	# Fallback if no leader elected
	return settings.node_name.lower() == settings.default_master.lower()


def _get_leader_url(settings: Settings) -> Optional[str]:
	"""Get the URL of the current cluster leader dynamically."""
	if _cluster_manager is None:
		return settings.default_master_url
	
	current_leader = _cluster_manager.current_leader
	if not current_leader:
		return settings.default_master_url
	
	# If we are the leader, no URL needed (handled locally)
	if current_leader.lower() == settings.node_name.lower():
		return None
	
	# Get leader URL from peer nodes
	for peer in settings.peer_nodes:
		if peer.name.lower() == current_leader.lower():
			return peer.base_url
	
	# Fallback to default master URL
	return settings.default_master_url


def _get_node_url(settings: Settings, node_name: str) -> Optional[str]:
	"""Get the URL for a specific node."""
	node_lower = node_name.lower()
	
	# If it's this node, return None (handle locally)
	if node_lower == settings.node_name.lower():
		return None
	
	# Check if node is simulated as down
	if _cluster_manager and _cluster_manager.is_node_simulated_down(node_lower):
		return None  # Can't forward to a down node
	
	# Find the node in peer list
	for peer in settings.peer_nodes:
		if peer.name.lower() == node_lower:
			return peer.base_url
	
	return None


def _check_leader_available():
	"""Check if the current leader is online. Raise 503 if leader is down."""
	if _cluster_manager is None:
		return
	
	current_leader = _cluster_manager.current_leader
	if current_leader and _cluster_manager.is_node_simulated_down(current_leader):
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail=f"Leader {current_leader} is simulated as offline - writes unavailable"
		)


def _check_writes_allowed():
	"""Check if writes are currently allowed (not gated for recovery)."""
	if _cluster_manager is None:
		return
	
	if not _cluster_manager.writes_allowed:
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail="Writes are currently gated - cluster recovery in progress"
		)


# Keep old name for backward compatibility but use new logic
def _is_master(settings: Settings) -> bool:
	"""Return True if the current node is the authoritative master/leader."""
	return _is_leader(settings)


async def _forward(request: Request, method: str, path: str, payload: Optional[dict] = None):
	"""Forward request to the current cluster leader (dynamic, not hardcoded)."""
	settings = get_settings()
	
	# Check if leader is available before forwarding
	_check_leader_available()
	
	# Get leader URL dynamically from cluster manager
	base_url = _get_leader_url(settings)
	if not base_url:
		raise HTTPException(
			status.HTTP_503_SERVICE_UNAVAILABLE,
			"Leader URL not available - cannot forward request"
		)
	
	client = request.app.state.http_client
	url = f"{base_url}{path}"
	
	try:
		if method == "POST":
			return await client.post_json(url, payload or {})
		if method == "PUT":
			return await client.put_json(url, payload or {})
		if method == "GET":
			return await client.get_json(url)
		if method == "DELETE":
			return await client.delete(url)
		raise RuntimeError(f"Unsupported forward method {method}")
	except Exception as e:
		# Check if this is a connection error indicating leader is down
		error_msg = str(e).lower()
		if "connect" in error_msg or "timeout" in error_msg or "refused" in error_msg:
			raise HTTPException(
				status.HTTP_503_SERVICE_UNAVAILABLE,
				f"Leader node unreachable at {base_url}: {e}"
			)
		raise


async def _forward_to_node(request: Request, node_name: str, method: str, path: str, payload: Optional[dict] = None):
	"""Forward request to a specific node (for partition-based routing)."""
	settings = get_settings()
	
	base_url = _get_node_url(settings, node_name)
	if not base_url:
		raise HTTPException(
			status.HTTP_503_SERVICE_UNAVAILABLE,
			f"Node {node_name} URL not available - cannot forward request"
		)
	
	client = request.app.state.http_client
	url = f"{base_url}{path}"
	
	try:
		if method == "POST":
			return await client.post_json(url, payload or {})
		if method == "PUT":
			return await client.put_json(url, payload or {})
		if method == "GET":
			return await client.get_json(url)
		if method == "DELETE":
			return await client.delete(url)
		raise RuntimeError(f"Unsupported forward method {method}")
	except Exception as e:
		error_msg = str(e).lower()
		if "connect" in error_msg or "timeout" in error_msg or "refused" in error_msg:
			raise HTTPException(
				status.HTTP_503_SERVICE_UNAVAILABLE,
				f"Node {node_name} unreachable at {base_url}: {e}"
			)
		raise


# ---------------------------------------------------------------------------
# CRUD Endpoints with Node Availability Checks
# ---------------------------------------------------------------------------

@router.post("/orders", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
async def create_order(order: OrderCreate, request: Request) -> OrderRead:
	settings = get_settings()
	
	# Check if writes are allowed (not gated for recovery)
	_check_writes_allowed()
	
	# If this node is simulated as down, forward to the leader
	if _cluster_manager and _cluster_manager.is_node_simulated_down(settings.node_name):
		# This node is "down" - forward to leader instead of rejecting
		response = await _forward(request, "POST", "/orders", payload=order.model_dump())
		return OrderRead(**response)
	
	pool = get_pool()
	promoted: bool = request.app.state.promoted
	
	# Determine which partition node should handle this order
	target_node = target_node_for_quantity(order.quantity, settings.partition_rule)
	this_node = settings.node_name.lower()
	
	# Check if we can handle this order locally
	can_handle_locally = (
		can_accept_partition(this_node, order.quantity, settings.partition_rule) or
		(this_node == "node0")  # node0 (central) can handle any partition
	)
	
	if can_handle_locally:
		# This node is responsible for this partition - handle locally
		return await crud.create_order(pool, order, settings.node_name)
	
	# This node can't handle the partition - forward to the correct partition node
	# If we're the leader (or promoted), we need to route to the correct partition node
	if _is_leader(settings) or promoted:
		# Check if target partition node is available
		target_url = _get_node_url(settings, target_node)
		if target_url:
			# Target node is available - forward to it
			response = await _forward_to_node(request, target_node, "POST", "/orders", payload=order.model_dump())
			return OrderRead(**response)
		else:
			# Target node is down - as leader, handle locally as fallback
			# The replication system will sync to the target node when it comes back
			return await crud.create_order(pool, order, settings.node_name)
	
	# We're not the leader and can't handle this partition - forward to leader
	response = await _forward(request, "POST", "/orders", payload=order.model_dump())
	return OrderRead(**response)


@router.get("/orders", response_model=list[OrderRead])
async def list_orders(request: Request):
	settings = get_settings()
	
	# If this node is simulated as down, forward to the leader
	if _cluster_manager and _cluster_manager.is_node_simulated_down(settings.node_name):
		response = await _forward(request, "GET", "/orders")
		return response
	
	pool = get_pool()
	if _is_leader(settings):
		orders, _ = await crud.list_orders(pool, page=1, limit=1000000)
		return orders
	response = await _forward(request, "GET", "/orders")
	return response


@router.get("/orders/local/all", response_model=list[OrderRead])
async def list_local_orders(request: Request):
	"""Get orders from THIS node's local database only (no forwarding).
	
	This endpoint ALWAYS returns local data regardless of node simulation state.
	It's used by the dashboard to show per-node order counts.
	"""
	# NOTE: Do NOT check node availability here - this endpoint must always work
	# so the dashboard can show data from each node's local database
	pool = get_pool()
	orders, _ = await crud.list_orders(pool, page=1, limit=1000000)
	return orders


@router.get("/orders/{order_id}", response_model=Optional[OrderRead])
async def read_order(order_id: UUID, request: Request, local: bool = False) -> Optional[OrderRead]:
	settings = get_settings()
	
	# If this node is simulated as down and not local-only, forward to the leader
	if not local and _cluster_manager and _cluster_manager.is_node_simulated_down(settings.node_name):
		response = await _forward(request, "GET", f"/orders/{order_id}")
		return OrderRead(**response) if response else None
	
	pool = get_pool()
	if _is_leader(settings) or local:
		return await crud.get_order(pool, order_id)
	response = await _forward(request, "GET", f"/orders/{order_id}")
	return OrderRead(**response) if response else None


@router.put("/orders/{order_id}", response_model=OrderRead)
async def update_order(order_id: UUID, order: OrderUpdate, request: Request) -> OrderRead:
	settings = get_settings()
	
	# Check if writes are allowed
	_check_writes_allowed()
	
	# If this node is simulated as down, forward to the leader
	if _cluster_manager and _cluster_manager.is_node_simulated_down(settings.node_name):
		response = await _forward(request, "PUT", f"/orders/{order_id}", payload=order.model_dump(exclude_none=True))
		return OrderRead(**response)
	
	pool = get_pool()
	promoted: bool = request.app.state.promoted
	
	if _is_leader(settings) or (promoted and order.quantity is not None and can_accept_partition(settings.node_name, order.quantity, settings.partition_rule)):
		updated = await crud.update_order(pool, order_id, order, settings.node_name)
		if not updated:
			raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Order not found")
		return updated
	
	response = await _forward(request, "PUT", f"/orders/{order_id}", payload=order.model_dump(exclude_none=True))
	return OrderRead(**response)


@router.delete("/orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(order_id: UUID, request: Request) -> None:
	settings = get_settings()
	
	# Check if writes are allowed
	_check_writes_allowed()
	
	# If this node is simulated as down, forward to the leader
	if _cluster_manager and _cluster_manager.is_node_simulated_down(settings.node_name):
		await _forward(request, "DELETE", f"/orders/{order_id}")
		return
	
	pool = get_pool()
	promoted: bool = request.app.state.promoted
	
	if _is_leader(settings) or promoted:
		deleted = await crud.delete_order(pool, order_id, settings.node_name)
		if not deleted:
			raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Order not found")
		return
	
	await _forward(request, "DELETE", f"/orders/{order_id}")
