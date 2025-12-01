"""Pydantic models shared across routers and workers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class OrderBase(BaseModel):
	quantity: int = Field(..., ge=1)
	payload: Optional[Dict[str, Any]] = None


class OrderCreate(OrderBase):
	order_id: Optional[UUID] = None


class OrderUpdate(BaseModel):
	quantity: Optional[int] = Field(None, ge=1)
	payload: Optional[Dict[str, Any]] = None


class OrderRead(OrderBase):
	order_id: UUID
	created_at: datetime
	updated_at: datetime


class PromoteToggle(BaseModel):
	promote: bool


class OpPayload(BaseModel):
	order_id: UUID
	quantity: int
	payload: Optional[Dict[str, Any]] = None


class OpRecord(BaseModel):
	op_id: UUID
	origin_node: str
	op_type: str
	table_name: str
	row_id: UUID
	payload: Dict[str, Any]
	ts: datetime
	lamport: int
	applied: bool
	applied_ts: Optional[datetime]

