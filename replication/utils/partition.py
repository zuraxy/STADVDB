"""Partition helper utilities shared across routes and workers."""

from __future__ import annotations


def can_accept_partition(node_name: str, quantity: int, threshold: int) -> bool:
    """Return True when the node is responsible for the provided quantity."""

    lower = node_name.lower()
    if lower.endswith("1"):
        return quantity <= threshold
    if lower.endswith("2"):
        return quantity > threshold
    return True

def target_node_for_quantity(quantity: int, threshold: int) -> str:
    """Map a quantity value to its logical node name."""

    return "node1" if quantity <= threshold else "node2"
