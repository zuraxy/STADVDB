"""Database helper functions for orders and replication logs."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from uuid import UUID, uuid4

from asyncpg import Pool

from .models import OpRecord, OrderCreate, OrderRead, OrderUpdate
from .utils import lamport as lamport_utils

_LOGGER = logging.getLogger(__name__)


def _utcnow() -> datetime:
	return datetime.now(timezone.utc)


def _order_payload(quantity: int, payload: Optional[dict]) -> dict:
	return {"quantity": quantity, "payload": payload}


async def create_order(pool: Pool, order: OrderCreate, origin_node: str) -> OrderRead:
	"""Insert an order and the matching op_log entry in one transaction."""
	import json

	order_id = order.order_id or uuid4()
	op_id = uuid4()
	now = _utcnow()

	async with pool.acquire() as conn:
		async with conn.transaction():
			lamport_value = await lamport_utils.next_lamport(conn, origin_node)
			await conn.execute(
				"""
				INSERT INTO orders (order_id, quantity, payload, created_at, updated_at)
				VALUES ($1, $2, $3, $4, $4)
				ON CONFLICT (order_id)
				DO UPDATE
					SET quantity = EXCLUDED.quantity,
						payload = EXCLUDED.payload,
						updated_at = EXCLUDED.updated_at
				""",
				order_id,
				order.quantity,
				order.payload,
				now,
			)
			# Convert op_log payload to JSON string for JSONB
			op_payload = _order_payload(order.quantity, order.payload)
			op_payload_json = json.dumps(op_payload)
			await conn.execute(
				"""
				INSERT INTO op_log (
					op_id, origin_node, op_type, table_name, row_id, payload,
					ts, lamport, applied, applied_ts
				) VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,$8,false,NULL)
				ON CONFLICT (op_id) DO NOTHING
				""",
				op_id,
				origin_node,
				"upsert",
				"orders",
				order_id,
				op_payload_json,
				now,
				lamport_value,
			)
	return OrderRead(
		order_id=order_id,
		quantity=order.quantity,
		payload=order.payload,
		created_at=now,
		updated_at=now,
	)


async def list_orders(pool: Pool, page: int, limit: int) -> Tuple[List[OrderRead], int]:
	offset = (page - 1) * limit
	async with pool.acquire() as conn:
		rows = await conn.fetch(
			"""
			SELECT order_id, quantity, payload, created_at, updated_at
			FROM orders
			ORDER BY updated_at DESC
			LIMIT $1 OFFSET $2
			""",
			limit,
			offset,
		)
		total = await conn.fetchval("SELECT COUNT(*) FROM orders")
	
	orders = []
	for row in rows:
		row_dict = dict(row)
		# Parse JSONB payload if it's a string
		if isinstance(row_dict.get('payload'), str):
			import json
			row_dict['payload'] = json.loads(row_dict['payload']) if row_dict['payload'] else None
		orders.append(OrderRead(**row_dict))
	
	return orders, int(total or 0)


async def update_order(pool: Pool, order_id: UUID, order: OrderUpdate, origin_node: str) -> Optional[OrderRead]:
	async with pool.acquire() as conn:
		async with conn.transaction():
			row = await conn.fetchrow(
				"SELECT order_id, quantity, payload, created_at, updated_at FROM orders WHERE order_id=$1",
				order_id,
			)
			if row is None:
				return None
			
			# Parse payload if it's a string
			existing_payload = row["payload"]
			if isinstance(existing_payload, str):
				import json
				existing_payload = json.loads(existing_payload) if existing_payload else None
			
			import json
			
			new_quantity = order.quantity or row["quantity"]
			new_payload = order.payload if order.payload is not None else existing_payload
			# Convert payload dict to JSON string for PostgreSQL JSONB
			payload_json = json.dumps(new_payload) if new_payload else None
			now = _utcnow()
			await conn.execute(
				"UPDATE orders SET quantity=$1, payload=$2::jsonb, updated_at=$3 WHERE order_id=$4",
				new_quantity,
				payload_json,
				now,
				order_id,
			)
			lamport_value = await lamport_utils.next_lamport(conn, origin_node)
			# Convert op_log payload to JSON string for JSONB
			op_payload = _order_payload(new_quantity, new_payload)
			op_payload_json = json.dumps(op_payload)
			await conn.execute(
				"""
				INSERT INTO op_log (
					op_id, origin_node, op_type, table_name, row_id, payload,
					ts, lamport, applied, applied_ts
				) VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,$8,false,NULL)
				ON CONFLICT (op_id) DO NOTHING
				""",
				uuid4(),
				origin_node,
				"upsert",
				"orders",
				order_id,
				op_payload_json,
				now,
				lamport_value,
			)
	return OrderRead(
		order_id=order_id,
		quantity=new_quantity,
		payload=new_payload,
		created_at=row["created_at"],
		updated_at=now,
	)


async def delete_order(pool: Pool, order_id: UUID, origin_node: str) -> bool:
	async with pool.acquire() as conn:
		async with conn.transaction():
			result = await conn.execute("DELETE FROM orders WHERE order_id=$1", order_id)
			deleted = result.endswith("DELETE 1")
			if deleted:
				lamport_value = await lamport_utils.next_lamport(conn, origin_node)
				# Convert empty dict to JSON string for JSONB
				op_payload_json = json.dumps({})
				await conn.execute(
					"""
					INSERT INTO op_log (
						op_id, origin_node, op_type, table_name, row_id, payload,
						ts, lamport, applied, applied_ts
					) VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,$8,false,NULL)
					ON CONFLICT (op_id) DO NOTHING
					""",
					uuid4(),
					origin_node,
					"delete",
					"orders",
					order_id,
					op_payload_json,
					_utcnow(),
					lamport_value,
				)
	return deleted


async def get_order(pool: Pool, order_id: UUID) -> Optional[OrderRead]:
	async with pool.acquire() as conn:
		row = await conn.fetchrow(
			"SELECT order_id, quantity, payload, created_at, updated_at FROM orders WHERE order_id=$1",
			order_id,
		)
	if row is None:
		return None
	
	row_dict = dict(row)
	# Parse JSONB payload if it's a string
	if isinstance(row_dict.get('payload'), str):
		import json
		row_dict['payload'] = json.loads(row_dict['payload']) if row_dict['payload'] else None
	
	return OrderRead(**row_dict)


async def insert_op_if_missing(conn, op_record: OpRecord) -> bool:
	"""Insert an op if absent. Returns True when actually inserted."""

	result = await conn.execute(
		"""
		INSERT INTO op_log (
			op_id, origin_node, op_type, table_name, row_id, payload,
			ts, lamport, applied, applied_ts
		) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
		ON CONFLICT (op_id) DO NOTHING
		""",
		op_record.op_id,
		op_record.origin_node,
		op_record.op_type,
		op_record.table_name,
		op_record.row_id,
		op_record.payload,
		op_record.ts,
		op_record.lamport,
		op_record.applied,
		op_record.applied_ts,
	)
	return result.endswith("INSERT 0 1")


def _row_to_op_record(row) -> OpRecord:
	data = dict(row)
	payload = data.get("payload")
	# Parse JSON string to dict if needed (asyncpg returns JSONB as string)
	if isinstance(payload, str):
		data["payload"] = json.loads(payload) if payload else {}
	else:
		data["payload"] = payload or {}
	return OpRecord(**data)


async def fetch_ops_since(
	conn,
	since_lamport: int,
	origin_node: Optional[str] = None,
	limit: int = 1000,
) -> List[OpRecord]:
	"""Return ops newer than the provided lamport value."""

	query = [
		"SELECT op_id, origin_node, op_type, table_name, row_id, payload, ts, lamport, applied, applied_ts",
		"FROM op_log",
		"WHERE lamport > $1",
	]
	params: List = [since_lamport]
	if origin_node:
		query.append("AND origin_node = $2")
		params.append(origin_node)
	query.append("ORDER BY lamport ASC, origin_node ASC LIMIT $%s" % (len(params) + 1))
	params.append(limit)
	rows = await conn.fetch(" ".join(query), *params)
	return [_row_to_op_record(row) for row in rows]


async def fetch_unapplied_ops(conn, limit: int = 100) -> List[OpRecord]:
	rows = await conn.fetch(
		"""
		SELECT op_id, origin_node, op_type, table_name, row_id, payload, ts, lamport, applied, applied_ts
		FROM op_log
		WHERE applied = false
		ORDER BY lamport ASC, origin_node ASC
		LIMIT $1
		""",
		limit,
	)
	return [_row_to_op_record(row) for row in rows]


async def apply_op_tx(conn, op_record: OpRecord) -> None:
	"""Apply an operation idempotently and mark it as applied."""

	async with conn.transaction():
		if op_record.op_type == "delete":
			await conn.execute("DELETE FROM orders WHERE order_id=$1", op_record.row_id)
		else:
			payload = op_record.payload or {}
			quantity = payload.get("quantity")
			order_payload = payload.get("payload")
			await conn.execute(
				"""
				INSERT INTO orders (order_id, quantity, payload, created_at, updated_at)
				VALUES ($1,$2,$3,$4,$4)
				ON CONFLICT (order_id)
				DO UPDATE SET quantity = EXCLUDED.quantity,
							  payload = EXCLUDED.payload,
							  updated_at = EXCLUDED.updated_at
				""",
				op_record.row_id,
				quantity,
				order_payload,
				op_record.ts,
			)
		await conn.execute(
			"UPDATE op_log SET applied=true, applied_ts=$2 WHERE op_id=$1",
			op_record.op_id,
			_utcnow(),
		)


async def insert_ack(conn, op_id: UUID, node: str) -> None:
	await conn.execute(
		"""
		INSERT INTO log_acknowledgements (op_id, node, ack_ts)
		VALUES ($1, $2, $3)
		ON CONFLICT (op_id, node) DO NOTHING
		""",
		op_id,
		node,
		_utcnow(),
	)
