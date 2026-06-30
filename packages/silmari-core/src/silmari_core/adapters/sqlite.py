"""SQLite adapter. Opens the database **read-only** via URI ``mode=ro`` and ``PRAGMA
query_only = ON`` so the engine physically rejects writes; an in-memory database is always
writable since it is ephemeral.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any

from ..source import DataSource

if TYPE_CHECKING:
    from ..audit import AuditLog
    from ..masking import MaskingPolicy


class SQLiteSource(DataSource):
    def __init__(
        self,
        database: str = ":memory:",
        *,
        read_only: bool = True,
        audit: AuditLog | None = None,
        masking: MaskingPolicy | None = None,
    ) -> None:
        super().__init__(audit, dialect="sqlite", masking=masking)
        read_only = read_only and database not in (":memory:", "")
        if read_only:
            self._con = sqlite3.connect(
                f"file:{database}?mode=ro", uri=True, check_same_thread=False
            )
        else:
            self._con = sqlite3.connect(database or ":memory:", check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        # Defense-in-depth: SELECT load_extension('...') parses as a read but loads native code.
        # Keep it off explicitly (also the CPython default). Builds without extension support
        # raise here and are already safe.
        try:
            self._con.enable_load_extension(False)
        except (AttributeError, sqlite3.NotSupportedError):
            pass
        if read_only:
            self._con.execute("PRAGMA query_only = ON")

    def _execute(self, sql: str) -> list[dict[str, Any]]:
        cur = self._con.execute(sql)
        return [dict(row) for row in cur.fetchall()]

    def _schema(self, table: str | None = None) -> Any:
        if table:
            name = table.split(".")[-1]
            if not name.isidentifier():
                return {table: []}
            cur = self._con.execute(f"PRAGMA table_info({name})")
            return {table: [{"column": r["name"], "type": r["type"]} for r in cur.fetchall()]}
        cur = self._con.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )
        return [r["name"] for r in cur.fetchall()]

    def close(self) -> None:
        self._con.close()
