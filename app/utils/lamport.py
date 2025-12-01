"""Lamport clock helpers."""

from __future__ import annotations

from typing import Tuple


def tick(current: int) -> int:
    """Increment the provided lamport counter."""

    return current + 1


def merge(local_clock: int, remote_clock: int) -> int:
    """Merge lamport values from two sources."""

    return max(local_clock, remote_clock) + 1


def compare(a: Tuple[int, str], b: Tuple[int, str]) -> int:
    """Compare lamport tuples for ordering, returns -1/0/1."""

    if a[0] < b[0]:
        return -1
    if a[0] > b[0]:
        return 1
    if a[1] < b[1]:
        return -1
    if a[1] > b[1]:
        return 1
    return 0


async def next_lamport(conn, origin_node: str) -> int:
    """Fetch the next lamport clock value for the node.

    We intentionally query the database to ensure durability across crashes.
    """

    current = await conn.fetchval(
        "SELECT COALESCE(MAX(lamport), 0) FROM op_log WHERE origin_node = $1",
        origin_node,
    )
    return tick(int(current or 0))
