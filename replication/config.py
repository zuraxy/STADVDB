"""Application configuration handling."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional


@dataclass(frozen=True)
class PeerNode:
	"""Represents the configuration required to contact a peer node."""

	name: str
	base_url: str


@dataclass(frozen=True)
class Settings:
	"""Typed configuration loaded from environment variables."""

	database_dsn: str
	node_name: str
	peer_nodes: List[PeerNode]
	poll_interval: float
	default_master: str
	default_master_url: Optional[str]
	promoted: bool
	partition_rule: int
	applier_interval: float
	node0_dsn: Optional[str]
	node1_dsn: Optional[str]
	node2_dsn: Optional[str]

	def peer_urls(self) -> List[str]:
		"""Return peer base URLs only."""

		return [peer.base_url for peer in self.peer_nodes]

	def dsn_for(self, node_label: str) -> Optional[str]:
		"""Return the configured DSN for a logical node name."""

		key = node_label.lower()
		mapping = {
			"node0": self.node0_dsn,
			"node1": self.node1_dsn,
			"node2": self.node2_dsn,
		}
		return mapping.get(key)


def _parse_bool(raw_value: Optional[str], default: bool = False) -> bool:
	if raw_value is None:
		return default
	return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_peers(raw_value: Optional[str]) -> List[PeerNode]:
	if not raw_value:
		return []

	candidates: List[str]
	raw_value = raw_value.strip()
	if raw_value.startswith("["):
		try:
			data = json.loads(raw_value)
		except json.JSONDecodeError as exc:  # pragma: no cover - config error
			raise ValueError("PEER_NODES must be a JSON array or comma list") from exc
		candidates = data if isinstance(data, list) else []
	else:
		candidates = [item.strip() for item in raw_value.split(",") if item.strip()]

	peers: List[PeerNode] = []
	for entry in candidates:
		if isinstance(entry, dict):
			name = str(entry.get("name") or "peer")
			url = str(entry.get("url") or entry.get("base_url"))
		else:
			text = str(entry)
			if "=" in text:
				name, url = text.split("=", 1)
			else:
				name, url = text, text
		url = url.strip()
		if not url:
			continue
		peers.append(PeerNode(name=name.strip() or "peer", base_url=url))
	return peers


@lru_cache()
def get_settings() -> Settings:
	"""Load configuration from the current environment only once."""

	database_dsn = os.getenv("DATABASE_DSN")
	if not database_dsn:
		raise RuntimeError("DATABASE_DSN must be provided")

	node_name = os.getenv("NODE_NAME", "node0")
	peer_nodes = _parse_peers(os.getenv("PEER_NODES"))
	default_master = os.getenv("DEFAULT_MASTER", "node0")
	default_master_url = os.getenv("DEFAULT_MASTER_URL")
	poll_interval = float(os.getenv("POLL_INTERVAL", "5"))
	applier_interval = float(os.getenv("APPLIER_INTERVAL", "2"))
	promoted = _parse_bool(os.getenv("PROMOTED"), default=False)
	partition_rule = int(os.getenv("PARTITION_RULE", "5"))
	node0_dsn = os.getenv("NODE0_DSN") or (database_dsn if node_name.lower() == "node0" else None)
	node1_dsn = os.getenv("NODE1_DSN") or (database_dsn if node_name.lower() == "node1" else None)
	node2_dsn = os.getenv("NODE2_DSN") or (database_dsn if node_name.lower() == "node2" else None)

	# Ensure local node always has a DSN entry for convenience
	if node_name.lower() == "node0" and not node0_dsn:
		node0_dsn = database_dsn
	if node_name.lower() == "node1" and not node1_dsn:
		node1_dsn = database_dsn
	if node_name.lower() == "node2" and not node2_dsn:
		node2_dsn = database_dsn

	if not default_master_url:
		for peer in peer_nodes:
			if peer.name == default_master:
				default_master_url = peer.base_url
				break

	return Settings(
		database_dsn=database_dsn,
		node_name=node_name,
		peer_nodes=peer_nodes,
		poll_interval=poll_interval,
		default_master=default_master,
		default_master_url=default_master_url,
		promoted=promoted,
		partition_rule=partition_rule,
		applier_interval=applier_interval,
		node0_dsn=node0_dsn,
		node1_dsn=node1_dsn,
		node2_dsn=node2_dsn,
	)
