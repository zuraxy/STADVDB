"""Mapping helpers for transaction isolation levels."""

from __future__ import annotations

from typing import Optional, Tuple

_ISOLATION_LOOKUP: dict[str, Tuple[str, Optional[str]]] = {
	"READ_UNCOMMITTED": ("READ COMMITTED", "PostgreSQL promotes READ UNCOMMITTED to READ COMMITTED."),
	"READ_COMMITTED": ("READ COMMITTED", None),
	"REPEATABLE_READ": ("REPEATABLE READ", None),
	"SERIALIZABLE": ("SERIALIZABLE", None),
}


def iso_clause_for(level: str) -> str:
	"""Return the SQL clause for a provided isolation level label."""

	return _ISOLATION_LOOKUP.get(level, ("READ COMMITTED", None))[0]


def iso_note_for(level: str) -> Optional[str]:
	"""Return any informational note associated with the level."""

	return _ISOLATION_LOOKUP.get(level, (None, None))[1]
