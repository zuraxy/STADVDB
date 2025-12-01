"""Replication endpoints exposed to peer nodes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from .. import crud
from ..db import get_pool

router = APIRouter(tags=["replication"])


@router.get("/oplog")
async def read_oplog(
	since_lamport: int = Query(-1, ge=-1),
	origin_node: Optional[str] = Query(None),
	limit: int = Query(1000, ge=1, le=5000),
):
	pool = get_pool()
	async with pool.acquire() as conn:
		ops = await crud.fetch_ops_since(conn, since_lamport, origin_node=origin_node, limit=limit)
	return [op.model_dump() for op in ops]
