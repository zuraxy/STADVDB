"""Order CRUD endpoints with leader-aware routing and node availability checks.

This module now supports:
1. Leader-aware routing: All writes go to current cluster leader (not hardcoded node0)
2. Node availability checks: Requests rejected with 503 if node is simulated as down
3. Full integration with ClusterManager for dynamic routing
4. Automatic failover: When local database is down, reroute to promoted followers
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from .. import crud
from ..config import Settings, get_settings
from ..db import get_pool
from ..models import OrderCreate, OrderRead, OrderUpdate
from ..utils.partition import can_accept_partition, target_node_for_quantity

_LOGGER = logging.getLogger(__name__)

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


def _is_database_error(exc: Exception) -> bool:
	"""Check if an exception indicates a database connection/availability issue."""
	error_msg = str(exc).lower()
	db_error_keywords = [
		"connection", "timeout", "refused", "closed", "pool", 
		"asyncpg", "postgresql", "database", "cannot connect",
		"connection pool", "too many connections", "server closed"
	]
	return any(keyword in error_msg for keyword in db_error_keywords)


async def _find_available_promoted_node(request: Request, settings: Settings) -> Optional[str]:
	"""Find a promoted follower node that can handle writes.
	
	Returns the base URL of an available promoted node, or None if none found.
	"""
	for peer in settings.peer_nodes:
		if peer.name.lower() == settings.node_name.lower():
			continue
		
		# Check if this peer is available and promoted
		try:
			result = await request.app.state.http_client.get_json_safe(
				f"{peer.base_url}/", default=None
			)
			if result and result.get("promoted"):
				_LOGGER.info("Found promoted node %s at %s", peer.name, peer.base_url)
				return peer.base_url
		except Exception:
			continue
	
	return None


async def _promote_and_forward(request: Request, method: str, path: str, quantity: int, payload: Optional[dict] = None):
	"""Promote a suitable follower and forward the request to it.
	
	This is called when the leader's database is down. We:
	1. Determine which follower should handle this write based on partition rules
	2. Tell that follower to promote itself
	3. Forward the write request to it
	
	If no suitable follower can be promoted, raises 503.
	"""
	settings = get_settings()
	
	# Determine which node should handle this write based on quantity
	target_node = target_node_for_quantity(quantity, settings.partition_rule)
	_LOGGER.info(
		"Leader DB down, promoting %s for quantity=%d (partition_rule=%d)",
		target_node, quantity, settings.partition_rule
	)
	
	# Find the target node's URL
	target_url = None
	fallback_url = None
	for peer in settings.peer_nodes:
		if peer.name.lower() == settings.node_name.lower():
			continue
		if peer.name.lower() == target_node.lower():
			target_url = peer.base_url
		elif fallback_url is None:
			fallback_url = peer.base_url
	
	# Try to promote and forward to target node first, then fallback
	for node_url in [target_url, fallback_url]:
		if not node_url:
			continue
		
		try:
			# Check if node is available
			health = await request.app.state.http_client.get_json_safe(
				f"{node_url}/health", default=None
			)
			if not health or health.get("status") != "ok":
				_LOGGER.warning("Node at %s not healthy, trying next", node_url)
				continue
			
			# Promote the node
			_LOGGER.info("Promoting node at %s", node_url)
			await request.app.state.http_client.post_json(
				f"{node_url}/promote",
				{"promote": True}
			)
			
			# Forward the request
			url = f"{node_url}{path}"
			if method == "POST":
				result = await request.app.state.http_client.post_json(url, payload or {})
			elif method == "PUT":
				result = await request.app.state.http_client.put_json(url, payload or {})
			elif method == "DELETE":
				result = await request.app.state.http_client.delete(url)
				return None
			else:
				raise RuntimeError(f"Unsupported method {method}")
			
			_LOGGER.info("Successfully forwarded %s %s to promoted node %s", method, path, node_url)
			return result
			
		except Exception as e:
			_LOGGER.warning("Failed to promote/forward to %s: %s", node_url, e)
			continue
	
	raise HTTPException(
		status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
		detail="Local database unavailable and could not promote any follower"
	)


async def _forward_to_promoted_follower(request: Request, method: str, path: str, payload: Optional[dict] = None, quantity: Optional[int] = None):
	"""Forward request to a promoted follower when local DB is unavailable.
	
	This is used when the leader's database is down but the API is still running.
	
	1. First, check if any follower is already promoted
	2. If not, promote a suitable follower based on the quantity (partition rules)
	3. Forward the request
	"""
	settings = get_settings()
	
	# First, check if there's already a promoted node
	promoted_url = await _find_available_promoted_node(request, settings)
	if promoted_url:
		client = request.app.state.http_client
		url = f"{promoted_url}{path}"
		
		try:
			if method == "POST":
				return await client.post_json(url, payload or {})
			if method == "PUT":
				return await client.put_json(url, payload or {})
			if method == "DELETE":
				await client.delete(url)
				return None
			raise RuntimeError(f"Unsupported forward method {method}")
		except Exception as e:
			_LOGGER.warning("Failed to forward to already-promoted node %s: %s", promoted_url, e)
			# Fall through to try promoting another node
	
	# No promoted node found (or it failed) - promote one based on the quantity
	if quantity is not None:
		return await _promote_and_forward(request, method, path, quantity, payload)
	
	# No quantity provided (e.g., delete) - just pick any available node
	for peer in settings.peer_nodes:
		if peer.name.lower() == settings.node_name.lower():
			continue
		
		try:
			health = await request.app.state.http_client.get_json_safe(
				f"{peer.base_url}/health", default=None
			)
			if health and health.get("status") == "ok":
				# Promote and forward
				await request.app.state.http_client.post_json(
					f"{peer.base_url}/promote",
					{"promote": True}
				)
				
				url = f"{peer.base_url}{path}"
				if method == "DELETE":
					await request.app.state.http_client.delete(url)
					return None
				elif method == "PUT":
					return await request.app.state.http_client.put_json(url, payload or {})
				elif method == "POST":
					return await request.app.state.http_client.post_json(url, payload or {})
		except Exception as e:
			_LOGGER.warning("Failed to promote/forward to %s: %s", peer.base_url, e)
			continue
	
	raise HTTPException(
		status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
		detail="Local database unavailable and no followers could be promoted"
	)


async def _forward(request: Request, method: str, path: str, payload: Optional[dict] = None):
	"""Forward request to the current cluster leader (dynamic, not hardcoded).
	
	This function also detects when the leader is unhealthy (database errors, 500s)
	and can trigger a self-promotion on the follower if configured.
	"""
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
		error_msg = str(e).lower()
		error_str = str(e)
		
		# Check if this is a connection error OR a leader database error
		is_connection_error = any(x in error_msg for x in ["connect", "timeout", "refused", "unreachable"])
		is_leader_db_error = any(x in error_msg for x in ["database", "internal server error", "500", "db", "postgresql", "asyncpg"])
		
		if is_connection_error or is_leader_db_error:
			# Leader is unhealthy - attempt to trigger promotion/recovery
			await _handle_leader_failure(request, base_url, error_str)
			
			raise HTTPException(
				status.HTTP_503_SERVICE_UNAVAILABLE,
				f"Leader node unhealthy at {base_url}: {e}. A follower may be promoted."
			)
		raise


async def _handle_leader_failure(request: Request, leader_url: str, error: str):
	"""Handle detected leader failure by attempting recovery actions.
	
	This is called when forwarding to the leader fails due to database or connection errors.
	If we're a follower that can accept partitions, we may self-promote.
	"""
	import logging
	logger = logging.getLogger(__name__)
	settings = get_settings()
	
	logger.warning(
		"Leader failure detected at %s from node %s: %s", 
		leader_url, settings.node_name, error
	)
	
	# If cluster_manager exists and supports auto-promotion, use it
	if _cluster_manager:
		try:
			# Mark leader as potentially down and trigger election
			current_leader = _cluster_manager.current_leader
			if current_leader:
				# Find the leader node name and mark it as having DB issues
				await _cluster_manager.report_leader_unhealthy(current_leader, error)
		except AttributeError:
			# ClusterManager doesn't have report_leader_unhealthy, use fallback
			pass
		except Exception as ex:
			logger.warning("Failed to report leader unhealthy to cluster manager: %s", ex)
	
	# Fallback: If this node can accept partitions and we detect consistent leader failure,
	# we can auto-promote. This allows the system to continue accepting writes.
	# Only do this if:
	# 1. We're not already promoted
	# 2. We're configured to allow auto-promotion
	if not request.app.state.promoted and getattr(settings, 'auto_promote_on_leader_failure', True):
		# Check leader health directly before promoting
		try:
			health = await request.app.state.http_client.get_json_safe(f"{leader_url}/health", default=None)
			if health and health.get("status") == "ok":
				# Leader is actually healthy, don't promote
				return
		except:
			pass  # Leader unhealthy, proceed with promotion consideration
		
		logger.warning(
			"Node %s auto-promoting due to leader failure at %s",
			settings.node_name, leader_url
		)
		request.app.state.promoted = True


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
		# BUT if local DB is down, failover to a promoted follower
		try:
			return await crud.create_order(pool, order, settings.node_name)
		except Exception as exc:
			if _is_database_error(exc):
				_LOGGER.warning(
					"Local database error on %s, attempting failover: %s",
					settings.node_name, exc
				)
				# Promote a follower based on partition rules and forward
				response = await _forward_to_promoted_follower(
					request, "POST", "/orders", 
					payload=order.model_dump(),
					quantity=order.quantity  # Pass quantity for partition-based promotion
				)
				return OrderRead(**response)
			raise  # Re-raise non-database errors
	
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
			try:
				return await crud.create_order(pool, order, settings.node_name)
			except Exception as exc:
				if _is_database_error(exc):
					_LOGGER.warning(
						"Local database error on leader %s, attempting failover: %s",
						settings.node_name, exc
					)
					response = await _forward_to_promoted_follower(
						request, "POST", "/orders", 
						payload=order.model_dump(),
						quantity=order.quantity  # Pass quantity for partition-based promotion
					)
					return OrderRead(**response)
				raise
	
	# We're not the leader and can't handle this partition - forward to leader
	response = await _forward(request, "POST", "/orders", payload=order.model_dump())
	return OrderRead(**response)


async def _fetch_orders_from_partitions(request: Request, settings: Settings) -> list[OrderRead]:
	"""Fetch orders from Node1 and Node2 and combine them.
	
	This is used as a fallback when Node0 (master) is unavailable.
	Node1 has orders with qty 1-5, Node2 has orders with qty >= 6.
	Combined, they should equal all orders.
	"""
	all_orders = []
	
	for peer in settings.peer_nodes:
		if peer.name.lower() == settings.node_name.lower():
			continue
		
		try:
			# Use /orders/local/all to get that node's local data directly
			orders_data = await request.app.state.http_client.get_json_safe(
				f"{peer.base_url}/orders/local/all", 
				default=[]
			)
			if orders_data:
				for order_data in orders_data:
					try:
						all_orders.append(OrderRead(**order_data))
					except Exception:
						pass  # Skip malformed orders
				_LOGGER.info("Fetched %d orders from %s", len(orders_data), peer.name)
		except Exception as exc:
			_LOGGER.warning("Failed to fetch orders from %s: %s", peer.name, exc)
	
	# Sort by updated_at descending (most recent first)
	all_orders.sort(key=lambda o: o.updated_at, reverse=True)
	return all_orders


@router.get("/orders", response_model=list[OrderRead])
async def list_orders(request: Request):
	settings = get_settings()
	
	# If this node is simulated as down, forward to the leader
	if _cluster_manager and _cluster_manager.is_node_simulated_down(settings.node_name):
		response = await _forward(request, "GET", "/orders")
		return response
	
	pool = get_pool()
	
	# Try local database first
	try:
		if _is_leader(settings):
			orders, _ = await crud.list_orders(pool, page=1, limit=1000000)
			return orders
	except Exception as exc:
		# Local DB failed - if we're the leader, try fetching from partitions
		if _is_leader(settings) and _is_database_error(exc):
			_LOGGER.warning("Leader DB unavailable, fetching from partition nodes: %s", exc)
			try:
				return await _fetch_orders_from_partitions(request, settings)
			except Exception as fallback_exc:
				_LOGGER.error("Failed to fetch from partitions: %s", fallback_exc)
				raise HTTPException(
					status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
					detail="Database temporarily unavailable. Please try again."
				)
		raise
	
	# Not leader - forward to leader, with fallback to partitions
	try:
		response = await _forward(request, "GET", "/orders")
		return response
	except HTTPException as exc:
		if exc.status_code in (502, 503, 504):
			# Leader unavailable, try fetching from partitions
			_LOGGER.warning("Leader unavailable for list, fetching from partitions")
			return await _fetch_orders_from_partitions(request, settings)
		raise


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
	
	# Try local database first
	try:
		if _is_leader(settings) or local:
			return await crud.get_order(pool, order_id)
	except Exception as exc:
		# Local DB failed - if we're the leader, try fetching from partition nodes
		if _is_leader(settings) and _is_database_error(exc):
			_LOGGER.warning("Leader DB unavailable for read, trying partitions: %s", exc)
			# Try to find the order in partition nodes
			for peer in settings.peer_nodes:
				if peer.name.lower() == settings.node_name.lower():
					continue
				try:
					order_data = await request.app.state.http_client.get_json_safe(
						f"{peer.base_url}/orders/{order_id}?local=true",
						default=None
					)
					if order_data:
						return OrderRead(**order_data)
				except Exception:
					continue
			return None  # Order not found in any partition
		raise
	
	# Not leader - forward to leader, with fallback to partitions
	try:
		response = await _forward(request, "GET", f"/orders/{order_id}")
		return OrderRead(**response) if response else None
	except HTTPException as exc:
		if exc.status_code in (502, 503, 504):
			# Leader unavailable, try partitions
			for peer in settings.peer_nodes:
				if peer.name.lower() == settings.node_name.lower():
					continue
				try:
					order_data = await request.app.state.http_client.get_json_safe(
						f"{peer.base_url}/orders/{order_id}?local=true",
						default=None
					)
					if order_data:
						return OrderRead(**order_data)
				except Exception:
					continue
			return None
		raise


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
		try:
			updated = await crud.update_order(pool, order_id, order, settings.node_name)
			if not updated:
				raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Order not found")
			return updated
		except HTTPException:
			raise  # Re-raise HTTP exceptions as-is
		except Exception as exc:
			if _is_database_error(exc):
				_LOGGER.warning(
					"Local database error on %s during update, attempting failover: %s",
					settings.node_name, exc
				)
				response = await _forward_to_promoted_follower(
					request, "PUT", f"/orders/{order_id}", 
					payload=order.model_dump(exclude_none=True),
					quantity=order.quantity  # May be None for updates without quantity change
				)
				return OrderRead(**response)
			raise
	
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
		try:
			deleted = await crud.delete_order(pool, order_id, settings.node_name)
			if not deleted:
				raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Order not found")
			return
		except HTTPException:
			raise  # Re-raise HTTP exceptions as-is
		except Exception as exc:
			if _is_database_error(exc):
				_LOGGER.warning(
					"Local database error on %s during delete, attempting failover: %s",
					settings.node_name, exc
				)
				await _forward_to_promoted_follower(request, "DELETE", f"/orders/{order_id}")
				return
			raise
	
	await _forward(request, "DELETE", f"/orders/{order_id}")
