"""Read-only SQL enforcement and table extraction, backed by a real SQL parser (sqlglot).

These are the core safety primitives:

- ``assert_read_only`` rejects anything that is not a single pure ``SELECT`` — including
  ``INSERT``/``UPDATE``/``DELETE``/DDL nested inside subqueries or CTEs, and multi-statement SQL.
- ``tables_referenced`` extracts the real tables a query reads **from the parse tree** (not by
  substring matching), excluding CTE names and aliases, so scoping cannot be fooled by a table
  name that appears only in a comment or a string literal.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from .errors import ReadOnlyViolation

# Expression types that read or modify server/session state; forbidden anywhere in the tree.
# Resolved defensively so a sqlglot version that renames/omits one of these does not break import.
_WRITE_NAMES = (
    "Insert",
    "Update",
    "Delete",
    "Merge",
    "Drop",
    "Create",
    "Alter",
    "TruncateTable",
    "Command",  # sqlglot's fallback for unmodeled statements (GRANT, CALL, ...)
    "Set",
)
_WRITE = tuple(getattr(exp, name) for name in _WRITE_NAMES if hasattr(exp, name))

# Allowed top-level statement types (read-only).
_READ_TOP = (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.Subquery)


def assert_read_only(sql: str, *, dialect: str | None = None) -> None:
    """Raise :class:`ReadOnlyViolation` unless ``sql`` is a single, pure read-only ``SELECT``.

    Any parse failure, multiple statements, a non-``SELECT`` top level, or a write/DDL node
    anywhere in the tree (e.g. inside a subquery or CTE) is rejected.
    """
    try:
        statements = [s for s in sqlglot.parse(sql, dialect=dialect) if s is not None]
    except Exception as exc:  # noqa: BLE001 — any parse failure is a rejection
        raise ReadOnlyViolation(f"could not parse SQL: {exc}") from exc

    if len(statements) != 1:
        raise ReadOnlyViolation("exactly one statement is allowed")

    stmt = statements[0]
    if not isinstance(stmt, _READ_TOP):
        raise ReadOnlyViolation(
            f"only read-only SELECT statements are allowed (got {type(stmt).__name__})"
        )

    bad = next(iter(stmt.find_all(*_WRITE)), None)
    if bad is not None:
        raise ReadOnlyViolation(f"write/DDL is not allowed (found {type(bad).__name__})")


def tables_referenced(sql: str, *, dialect: str | None = None) -> set[str]:
    """Return the real tables ``sql`` reads, as lowercased qualified names (e.g. ``demo.orders``).

    CTE names and table aliases are excluded; extraction is parse-based, so a table name that
    appears only in a comment or string literal is not counted.
    """
    try:
        stmt = sqlglot.parse_one(sql, dialect=dialect)
    except Exception as exc:  # noqa: BLE001
        raise ReadOnlyViolation(f"could not parse SQL: {exc}") from exc

    cte_names = {cte.alias_or_name.lower() for cte in stmt.find_all(exp.CTE)}

    tables: set[str] = set()
    for table in stmt.find_all(exp.Table):
        if not table.db and not table.catalog and table.name.lower() in cte_names:
            continue  # reference to a CTE, not a real table
        parts = [p for p in (table.catalog, table.db, table.name) if p]
        tables.add(".".join(parts).lower())
    return tables
