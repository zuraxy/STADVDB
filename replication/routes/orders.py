"""Order CRUD endpoints with master routing rules."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from .. import crud
from ..config import Settings, get_settings
from ..db import get_pool
from ..models import OrderCreate, OrderRead, OrderUpdate, PaginatedOrders

router = APIRouter(tags=["orders"])


def _can_accept_partition(node_name: str, quantity: int, threshold: int) -> bool:
	lower = node_name.lower()
	if lower.endswith("1"):
		return quantity <= threshold
	if lower.endswith("2"):
		return quantity > threshold
	return True


def _is_master(settings: Settings) -> bool:
	return settings.node_name == settings.default_master


async def _forward(request: Request, method: str, path: str, payload: Optional[dict] = None):
	settings = get_settings()
	base_url = settings.default_master_url
	if not base_url:
		raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Master URL not configured")
	client = request.app.state.http_client
	url = f"{base_url}{path}"
	if method == "POST":
		return await client.post_json(url, payload or {})
	if method == "PUT":
		return await client.put_json(url, payload or {})
	if method == "GET":
		return await client.get_json(url)
	if method == "DELETE":
		return await client.delete(url)
	raise RuntimeError(f"Unsupported forward method {method}")


@router.post("/orders", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
async def create_order(order: OrderCreate, request: Request) -> OrderRead:
	settings = get_settings()
	pool = get_pool()
	promoted: bool = request.app.state.promoted
	# TODO: Introduce a distributed transaction coordinator for cross-partition writes.
	if _is_master(settings) or (promoted and _can_accept_partition(settings.node_name, order.quantity, settings.partition_rule)):
		return await crud.create_order(pool, order, settings.node_name)
	response = await _forward(request, "POST", "/orders", payload=order.model_dump())
	return OrderRead(**response)


@router.get("/orders", response_model=list[OrderRead])
async def list_orders(request: Request):
	settings = get_settings()
	pool = get_pool()
	if _is_master(settings):
		orders, _ = await crud.list_orders(pool, page=1, limit=10000)
		return orders
	response = await _forward(request, "GET", "/orders")
	return response


@router.get("/orders/{order_id}", response_model=Optional[OrderRead])
async def read_order(order_id: UUID, request: Request, local: bool = False) -> Optional[OrderRead]:
	settings = get_settings()
	pool = get_pool()
	if _is_master(settings) or local:
		return await crud.get_order(pool, order_id)
	response = await _forward(request, "GET", f"/orders/{order_id}")
	return OrderRead(**response) if response else None


@router.put("/orders/{order_id}", response_model=OrderRead)
async def update_order(order_id: UUID, order: OrderUpdate, request: Request) -> OrderRead:
	settings = get_settings()
	pool = get_pool()
	promoted: bool = request.app.state.promoted
	if _is_master(settings) or (promoted and order.quantity is not None and _can_accept_partition(settings.node_name, order.quantity, settings.partition_rule)):
		updated = await crud.update_order(pool, order_id, order, settings.node_name)
		if not updated:
			raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Order not found")
		return updated
	response = await _forward(request, "PUT", f"/orders/{order_id}", payload=order.model_dump(exclude_none=True))
	return OrderRead(**response)


@router.delete("/orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(order_id: UUID, request: Request) -> None:
	settings = get_settings()
	pool = get_pool()
	promoted: bool = request.app.state.promoted
	if _is_master(settings) or promoted:
		deleted = await crud.delete_order(pool, order_id, settings.node_name)
		if not deleted:
			raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Order not found")
		return
	await _forward(request, "DELETE", f"/orders/{order_id}")
