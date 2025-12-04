"""FastAPI application entrypoint."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import crud
from .config import get_settings
from .db import close_db, get_pool, init_db
from .orchestrator import TransactionOrchestrator
from .recovery import RecoveryManager
from .recovery_tests import RecoveryTestRunner
from .cluster_manager import ClusterManager
from .routes import admin, orchestrator as orchestrator_routes, orders, replication, recovery as recovery_routes
from .routes import recovery_tests as recovery_tests_routes
from .routes import cluster as cluster_routes
from .utils.http_client import HTTPClient
from .workers.applier import ApplierWorker
from .workers.replicator import ReplicatorWorker

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

settings = get_settings()
app = FastAPI(title="Distributed Replicator", version="0.1.0")

# Add CORS middleware for frontend
app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

app.state.promoted = settings.promoted
app.include_router(admin.router)
app.include_router(orders.router)
app.include_router(replication.router)
app.include_router(orchestrator_routes.router)
app.include_router(recovery_routes.router)
app.include_router(recovery_tests_routes.router)
app.include_router(cluster_routes.router)


@app.on_event("startup")
async def on_startup() -> None:  # pragma: no cover - exercised via integration tests
	await init_db(settings.database_dsn)
	pool = get_pool()
	async with pool.acquire() as conn:
		await crud.ensure_replication_metadata(conn)
	app.state.promoted = settings.promoted
	app.state.http_client = HTTPClient()
	
	# Initialize cluster manager first so workers can use it
	app.state.cluster_manager = ClusterManager(
		pool, settings, app.state.http_client,
		get_promoted_flag=lambda: bool(app.state.promoted),
		set_promoted_flag=lambda v: setattr(app.state, 'promoted', v),
	)
	
	# Create a callback to check if this node is simulated as down
	def is_node_paused() -> bool:
		if hasattr(app.state, 'cluster_manager'):
			return app.state.cluster_manager.is_node_simulated_down(settings.node_name)
		return False
	
	app.state.replicator = ReplicatorWorker(pool, settings, app.state.http_client, is_paused=is_node_paused)
	app.state.applier = ApplierWorker(pool, settings, is_paused=is_node_paused)
	app.state.orchestrator = TransactionOrchestrator(
		settings,
		lambda: bool(app.state.promoted),
		http_client=app.state.http_client,
	)
	app.state.recovery_manager = RecoveryManager(
		pool, settings, app.state.http_client,
		get_promoted_flag=lambda: bool(app.state.promoted)
	)
	app.state.recovery_test_runner = RecoveryTestRunner(
		pool, settings, app.state.http_client
	)
	
	# Inject cluster manager into orders routes for leader-aware routing
	from .routes.orders import set_cluster_manager
	set_cluster_manager(app.state.cluster_manager)
	
	await app.state.replicator.start()
	await app.state.applier.start()
	await app.state.cluster_manager.start()
	LOGGER.info("Startup complete for node %s (cluster manager injected)", settings.node_name)


@app.on_event("shutdown")
async def on_shutdown() -> None:  # pragma: no cover - exercised via integration tests
	if hasattr(app.state, "cluster_manager"):
		await app.state.cluster_manager.stop()
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
