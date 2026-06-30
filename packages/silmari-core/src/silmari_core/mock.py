"""In-memory ``MockSource`` — a dict-backed DataSource for tests and simple demos.

Read-only by construction (there is no write path). ``_execute`` resolves the first table from
the parsed SQL and returns its rows, honoring a trailing ``LIMIT``. Not a SQL engine — joins,
``WHERE`` and aggregates are not interpreted; use a real adapter for those.
"""

from __future__ import annotations

import re
from typing import Any

from .audit import AuditLog
from .masking import MaskingPolicy
from .source import DataSource
from .sql import tables_referenced

_LIMIT_RE = re.compile(r"\blimit\s+(\d+)", re.IGNORECASE)


class MockSource(DataSource):
    def __init__(
        self,
        tables: dict[str, list[dict[str, Any]]],
        *,
        audit: AuditLog | None = None,
        masking: MaskingPolicy | None = None,
    ) -> None:
        super().__init__(audit, dialect=None, masking=masking)
        self._tables = {name.lower(): rows for name, rows in tables.items()}

    def _rows_for(self, sql: str) -> list[dict[str, Any]]:
        refs = sorted(tables_referenced(sql))
        if not refs:
            return []
        key = refs[0]
        if key in self._tables:
            return self._tables[key]
        bare = key.split(".")[-1]
        for name, rows in self._tables.items():
            if name.split(".")[-1] == bare:
                return rows
        return []

    def _execute(self, sql: str) -> list[dict[str, Any]]:
        rows = list(self._rows_for(sql))
        match = _LIMIT_RE.search(sql)
        if match:
            rows = rows[: int(match.group(1))]
        return rows

    def _schema(self, table: str | None = None) -> Any:
        if table:
            rows = self._rows_for(f"SELECT * FROM {table}")
            return {table: list(rows[0].keys()) if rows else []}
        return {
            name: (list(rows[0].keys()) if rows else []) for name, rows in self._tables.items()
        }
