"""
Read-only endpoints for frontend consumption.
Minimal API surface for displaying order data.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from uuid import UUID
from typing import List

from ..db import get_db_pool
from ..crud import get_all_orders, count_orders, get_node_stats, get_order
from ..models import OrderRead
from ..config import get_config

router = APIRouter()


@router.get("/orders", response_model=List[OrderRead])
async def list_orders(
	limit: int = Query(100, ge=1, le=1000),
	offset: int = Query(0, ge=0),
	pool=Depends(get_db_pool)
):
	"""
	Fetch all orders with pagination.
	
	- **limit**: Maximum number of orders to return (1-1000, default 100)
	- **offset**: Number of orders to skip (default 0)
	"""
	try:
		return await get_all_orders(pool, limit, offset)
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Failed to fetch orders: {str(e)}")


@router.get("/orders/{order_id}", response_model=OrderRead)
async def get_order_by_id(
	order_id: UUID,
	pool=Depends(get_db_pool)
):
	"""
	Fetch a specific order by ID.
	
	- **order_id**: UUID of the order
	"""
	order = await get_order(pool, order_id)
	if not order:
		raise HTTPException(status_code=404, detail="Order not found")
	return order


@router.get("/count")
async def get_order_count(pool=Depends(get_db_pool)):
	"""
	Get total count of orders.
	
	Returns: {"count": int}
	"""
	try:
		count = await count_orders(pool)
		return {"count": count}
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Failed to count orders: {str(e)}")


@router.get("/node-stats")
async def get_stats(pool=Depends(get_db_pool)):
	"""
	Get statistics for the current node.
	
	Returns node statistics including total orders, pending operations, etc.
	"""
	try:
		config = get_config()
		stats = await get_node_stats(pool, config.node_name)
		return stats
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Failed to fetch stats: {str(e)}")
