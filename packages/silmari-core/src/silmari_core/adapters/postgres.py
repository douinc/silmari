# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""PostgreSQL adapter.

Enforces read-only at the **session level** (``SET default_transaction_read_only = on``) so the
backend refuses writes even behind the SQL guard. For the strongest, role-enforced guarantee,
connect with a dedicated **read-only database role** (the headline "point Silmari at a read-only
DB role"): then writes are denied by the server regardless of the session setting.

``psycopg`` (v3) is an **optional** dependency — install the ``postgres`` extra
(``pip install 'silmari-core[postgres]'``). It is imported lazily so the rest of the library works
without it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..source import DataSource

if TYPE_CHECKING:
    from ..audit import AuditLog
    from ..masking import MaskingPolicy


def _connect(dsn: str, *, read_only: bool = True) -> Any:
    """Open a psycopg connection (lazy import keeps psycopg an optional dependency)."""
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - exercised via a faked module in tests
        raise ImportError(
            "PostgresSource requires the 'postgres' extra: pip install 'silmari-core[postgres]'"
        ) from exc
    conn = psycopg.connect(dsn, autocommit=True)
    if read_only:
        # Session-level read-only: every transaction on this connection refuses writes. This is
        # defense-in-depth behind the SQL guard — pair it with a read-only DB role in production.
        conn.execute("SET default_transaction_read_only = on")
    return conn


class PostgresSource(DataSource):
    def __init__(
        self,
        dsn: str,
        *,
        read_only: bool = True,
        audit: AuditLog | None = None,
        masking: MaskingPolicy | None = None,
    ) -> None:
        super().__init__(audit, dialect="postgres", masking=masking)
        self._con = _connect(dsn, read_only=read_only)

    def _execute(self, sql: str) -> list[dict[str, Any]]:
        with self._con.cursor() as cur:
            cur.execute(sql)
            if cur.description is None:  # e.g. a statement with no result set
                return []
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]

    def _schema(self, table: str | None = None) -> Any:
        if table:
            parts = table.split(".")
            params: tuple[str, ...]
            if len(parts) == 2:
                where, params = "table_schema = %s AND table_name = %s", (parts[0], parts[1])
            else:
                where, params = "table_name = %s", (parts[-1],)
            with self._con.cursor() as cur:
                cur.execute(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    f"WHERE {where} ORDER BY ordinal_position",
                    params,
                )
                return {table: [{"column": r[0], "type": r[1]} for r in cur.fetchall()]}
        with self._con.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
                "ORDER BY table_name"
            )
            return [r[0] for r in cur.fetchall()]

    def close(self) -> None:
        self._con.close()
