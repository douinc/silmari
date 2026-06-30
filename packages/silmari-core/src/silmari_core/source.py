# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""DataSource: governed, read-only, scoped, audited data access.

``DataSource`` is the abstract base every adapter extends. It implements the full public surface
(``query``/``sample``/``stats``/``schema``/``scoped``) on top of two adapter methods
(``_execute``/``_schema``). The read-only guard (:func:`silmari_core.sql.assert_read_only`) and
the audit write happen **in the base class**, so no adapter can bypass them.

``ScopedSource`` wraps a ``DataSource`` and rejects any query that reads a table outside the
declared :class:`DataAccess` allowlist — using parse-based table extraction, so the check cannot
be fooled by a table name in a comment or string literal.
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .audit import AuditLog
from .errors import ScopeViolation
from .masking import MaskingPolicy, NoMasking
from .sql import assert_read_only, tables_referenced


@dataclass
class DataAccess:
    """Declared read scope for a bot/agent. Empty ``tables`` means unscoped (no restriction)."""

    tables: list[str] = field(default_factory=list)
    scope: str = ""
    as_of: str = ""


def _first_table(sql: str, dialect: str | None = None) -> str:
    try:
        refs = sorted(tables_referenced(sql, dialect=dialect))
    except Exception:  # noqa: BLE001 — audit target is best-effort
        return ""
    return refs[0] if refs else ""


def _matches(referenced: str, declared: str) -> bool:
    # Strict, exact (case-insensitive) match. Bare and qualified names do NOT cross-match, so a
    # scope of ["orders"] never admits "evil.orders", and ["demo.orders"] never admits a bare
    # "orders" the engine could resolve to a different schema via search_path. Declare the scope
    # and write queries with consistent qualification.
    return referenced.lower() == declared.lower()


class DataSource(ABC):
    def __init__(
        self,
        audit: AuditLog | None = None,
        *,
        dialect: str | None = None,
        masking: MaskingPolicy | None = None,
    ) -> None:
        self.audit = audit or AuditLog()
        self._dialect = dialect
        self._masking: MaskingPolicy = masking or NoMasking()
        # Serialize backend access: one source may be shared across concurrent runs (scheduler
        # thread pool, daemon start_run). A single DB connection is not safe for concurrent use.
        self._lock = threading.RLock()

    @property
    def masking(self) -> MaskingPolicy:
        """The masking policy applied to ``sample()`` (and by callers that mask query results)."""
        return self._masking

    @classmethod
    def connect(
        cls,
        url: str,
        *,
        read_only: bool = True,
        audit: AuditLog | None = None,
        masking: MaskingPolicy | None = None,
    ) -> DataSource:
        """Open a read-only data source from a URL (``duckdb:///...`` or ``sqlite:///...``)."""
        from .adapters import connect as _connect

        return _connect(url, read_only=read_only, audit=audit, masking=masking)

    # --- adapter implements only these two ---
    @abstractmethod
    def _execute(self, sql: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    def _schema(self, table: str | None = None) -> Any: ...

    # --- public surface (guard + audit live here; adapters cannot bypass) ---
    def query(self, sql: str, *, run_id: str = "") -> list[dict[str, Any]]:
        target = _first_table(sql, self._dialect)
        try:
            assert_read_only(sql, dialect=self._dialect)
        except Exception:
            self.audit.record("query", run_id=run_id, target=target, outcome="denied")
            raise
        start = time.perf_counter()
        try:
            with self._lock:
                rows = self._execute(sql)
        except Exception:
            duration_ms = int((time.perf_counter() - start) * 1000)
            self.audit.record(
                "query", run_id=run_id, target=target, duration_ms=duration_ms, outcome="error"
            )
            raise
        duration_ms = int((time.perf_counter() - start) * 1000)
        self.audit.record(
            "query",
            run_id=run_id,
            target=target,
            row_count=len(rows),
            duration_ms=duration_ms,
        )
        return rows

    def sample(self, table: str, n: int = 5, *, run_id: str = "") -> list[dict[str, Any]]:
        rows = self.query(f"SELECT * FROM {table} LIMIT {int(n)}", run_id=run_id)
        return [self._masking.mask(row) for row in rows]

    def stats(self, table: str, column: str, *, run_id: str = "") -> list[dict[str, Any]]:
        # Mask the grouped column too — otherwise stats() would leak the full distinct set of a
        # sensitive column under the guise of frequency counts (sample() already masks).
        rows = self.query(
            f"SELECT {column}, COUNT(*) AS n FROM {table} GROUP BY {column} LIMIT 50",
            run_id=run_id,
        )
        return [self._masking.mask(row) for row in rows]

    def schema(self, table: str | None = None, *, run_id: str = "") -> Any:
        with self._lock:
            result = self._schema(table)
        self.audit.record("schema", run_id=run_id, target=table or "")
        return result

    def scoped(self, access: DataAccess, *, run_id: str = "") -> ScopedSource:
        return ScopedSource(self, access, run_id)

    def close(self) -> None:  # noqa: B027 — optional lifecycle hook; adapters override
        """Release any underlying connection. No-op by default; adapters override."""


class ScopedSource:
    """A table-scoped view of a :class:`DataSource`."""

    def __init__(self, source: DataSource, access: DataAccess, run_id: str = "") -> None:
        self._source = source
        self._access = access
        self._run_id = run_id

    def _check(self, sql: str) -> None:
        allowed = self._access.tables
        if not allowed:
            return  # empty allowlist == unscoped
        # A file/function data source (e.g. DuckDB read_csv(), FROM 'file.parquet') resolves to an
        # unresolved/empty reference that matches nothing in the allowlist — so scoping fails
        # closed rather than letting an unrecognized source through. See tests/test_threat_model.py.
        for referenced in tables_referenced(sql, dialect=self._source._dialect):
            if not any(_matches(referenced, declared) for declared in allowed):
                self._source.audit.record(
                    "query", run_id=self._run_id, target=referenced, outcome="denied"
                )
                raise ScopeViolation(
                    f"query reads a table outside the declared scope: {referenced!r} "
                    f"(allowed: {sorted(allowed)})"
                )

    def query(self, sql: str) -> list[dict[str, Any]]:
        self._check(sql)
        return self._source.query(sql, run_id=self._run_id)

    def sample(self, table: str, n: int = 5) -> list[dict[str, Any]]:
        self._check(f"SELECT * FROM {table}")
        return self._source.sample(table, n, run_id=self._run_id)

    def stats(self, table: str, column: str) -> list[dict[str, Any]]:
        self._check(f"SELECT * FROM {table}")
        return self._source.stats(table, column, run_id=self._run_id)

    def schema(self, table: str | None = None) -> Any:
        return self._source.schema(table, run_id=self._run_id)
