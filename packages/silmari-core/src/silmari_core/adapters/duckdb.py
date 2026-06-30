"""DuckDB adapter. Opens the database **read-only** so the engine physically rejects writes
(``read_only=True``); an in-memory database is always writable since it is ephemeral.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import duckdb

from ..source import DataSource

if TYPE_CHECKING:
    from ..audit import AuditLog
    from ..masking import MaskingPolicy


class DuckDBSource(DataSource):
    def __init__(
        self,
        database: str = ":memory:",
        *,
        read_only: bool = True,
        audit: AuditLog | None = None,
        masking: MaskingPolicy | None = None,
    ) -> None:
        super().__init__(audit, dialect="duckdb", masking=masking)
        read_only = read_only and database != ":memory:"
        self._con = duckdb.connect(database=database, read_only=read_only)

    def _execute(self, sql: str) -> list[dict[str, Any]]:
        cur = self._con.execute(sql)
        if cur.description is None:
            return []
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]

    def _schema(self, table: str | None = None) -> Any:
        if table:
            rows = self._con.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE lower(table_name) = lower(?)",
                [table.split(".")[-1]],
            ).fetchall()
            return {table: [{"column": c, "type": t} for c, t in rows]}
        rows = self._con.execute(
            "SELECT table_schema, table_name FROM information_schema.tables ORDER BY 1, 2"
        ).fetchall()
        return [f"{s}.{t}" for s, t in rows]

    def close(self) -> None:
        self._con.close()
