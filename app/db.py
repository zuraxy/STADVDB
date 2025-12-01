"""Database connection helpers built on asyncpg pools."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import asyncpg

_LOGGER = logging.getLogger(__name__)
_POOL: Optional[asyncpg.Pool] = None
_POOL_LOCK = asyncio.Lock()


async def init_db(dsn: str, **pool_kwargs: Any) -> asyncpg.Pool:
	"""Initialise the asyncpg pool once and return it."""

	global _POOL
	async with _POOL_LOCK:
		if _POOL is None:
			min_size = pool_kwargs.pop("min_size", 1)
			max_size = pool_kwargs.pop("max_size", 10)
			_LOGGER.info("Creating asyncpg pool min=%s max=%s", min_size, max_size)
			_POOL = await asyncpg.create_pool(dsn=dsn, min_size=min_size, max_size=max_size, **pool_kwargs)
	return _POOL


def get_pool() -> asyncpg.Pool:
	"""Return the initialised pool or raise if unavailable."""

	if _POOL is None:
		raise RuntimeError("Database pool has not been initialised")
	return _POOL


async def close_db() -> None:
	"""Dispose of the pool during application shutdown."""

	global _POOL
	async with _POOL_LOCK:
		if _POOL is not None:
			_LOGGER.info("Closing asyncpg pool")
			await _POOL.close()
			_POOL = None


async def execute(query: str, *args: Any) -> str:
	pool = get_pool()
	async with pool.acquire() as conn:
		return await conn.execute(query, *args)


async def executemany(query: str, args_iterable: Any) -> None:
	pool = get_pool()
	async with pool.acquire() as conn:
		await conn.executemany(query, args_iterable)


async def fetch(query: str, *args: Any) -> list[asyncpg.Record]:
	pool = get_pool()
	async with pool.acquire() as conn:
		return await conn.fetch(query, *args)


async def fetchrow(query: str, *args: Any) -> Optional[asyncpg.Record]:
	pool = get_pool()
	async with pool.acquire() as conn:
		return await conn.fetchrow(query, *args)
