"""FastAPI application entrypoint."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from . import crud
from .config import get_settings
from .db import close_db, get_pool, init_db
from .orchestrator import TransactionOrchestrator
from .routes import admin, orchestrator as orchestrator_routes, orders, replication
from .utils.http_client import HTTPClient
from .workers.applier import ApplierWorker
from .workers.replicator import ReplicatorWorker

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

settings = get_settings()
app = FastAPI(title="Distributed Replicator", version="0.1.0")
app.state.promoted = settings.promoted
app.include_router(admin.router)
app.include_router(orders.router)
app.include_router(replication.router)
app.include_router(orchestrator_routes.router)


@app.on_event("startup")
async def on_startup() -> None:  # pragma: no cover - exercised via integration tests
	await init_db(settings.database_dsn)
	pool = get_pool()
	async with pool.acquire() as conn:
		await crud.ensure_replication_metadata(conn)
	app.state.promoted = settings.promoted
	app.state.http_client = HTTPClient()
	app.state.replicator = ReplicatorWorker(pool, settings, app.state.http_client)
	
	# Create is_leader callback that checks:
	# 1. If this is the default_master, OR
	# 2. If this node has been promoted (app.state.promoted)
	def is_current_leader() -> bool:
		if settings.node_name.lower() == settings.default_master.lower():
			return True
		return bool(app.state.promoted)
	
	app.state.applier = ApplierWorker(pool, settings, is_leader=is_current_leader)
	app.state.orchestrator = TransactionOrchestrator(
		settings,
		lambda: bool(app.state.promoted),
		http_client=app.state.http_client,
	)
	await app.state.replicator.start()
	await app.state.applier.start()
	LOGGER.info("Startup complete for node %s", settings.node_name)


@app.on_event("shutdown")
async def on_shutdown() -> None:  # pragma: no cover - exercised via integration tests
	if hasattr(app.state, "replicator"):
		await app.state.replicator.stop()
	if hasattr(app.state, "applier"):
		await app.state.applier.stop()
	if hasattr(app.state, "http_client"):
		await app.state.http_client.close()
	await close_db()


@app.get("/")
async def root() -> dict:
	return {"node": settings.node_name, "promoted": app.state.promoted}


__all__ = ["app"]
