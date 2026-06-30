# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Runnable safety demo: ``silmari-demo`` (or ``run_demo()``).

Seeds a tiny DuckDB database, opens it read-only through Silmari, and shows the four guarantees:
a write is blocked by the parser guard *and* by the engine, an out-of-scope read is blocked, PII
is redacted on ``sample()``, and every access is audited.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import duckdb

from .adapters import connect
from .errors import ReadOnlyViolation, ScopeViolation
from .masking import default_masking
from .source import DataAccess


def _seed(path: str) -> None:
    con = duckdb.connect(path)
    con.execute("CREATE TABLE orders(id INTEGER, customer_id INTEGER, total INTEGER)")
    con.execute("INSERT INTO orders VALUES (1, 10, 100), (2, 11, 50)")
    con.execute("CREATE TABLE customers(id INTEGER, name VARCHAR, email VARCHAR)")
    con.execute(
        "INSERT INTO customers VALUES "
        "(10, 'Ada', 'ada@example.com'), (11, 'Lin', 'lin@example.com')"
    )
    con.close()


def run_demo(path: str | None = None) -> dict[str, Any]:
    """Run the demo, print a narrative, and return a results dict (used by tests)."""
    if path is None:
        path = str(Path(tempfile.mkdtemp(prefix="silmari-demo-")) / "demo.duckdb")
    _seed(path)

    results: dict[str, Any] = {}
    src = connect(f"duckdb:///{path}", masking=default_masking())

    # 1) a normal read works and is audited
    results["read_rows"] = src.query("SELECT id, total FROM orders ORDER BY id", run_id="demo")

    # 2) a write is rejected by the parser guard
    try:
        src.query("DROP TABLE orders")
    except ReadOnlyViolation as exc:
        results["drop_blocked"] = str(exc)

    # 3) the engine itself rejects writes even if the guard were bypassed
    con = getattr(src, "_con", None)
    if con is not None:
        try:
            con.execute("DELETE FROM orders")
            results["db_write_blocked"] = False
        except Exception as exc:  # noqa: BLE001 — demonstrating the engine's own rejection
            results["db_write_blocked"] = type(exc).__name__

    # 4) scope: only `orders` is allowed, so reading `customers` is blocked
    scoped = src.scoped(DataAccess(tables=["orders"]), run_id="demo")
    try:
        scoped.query("SELECT * FROM customers")
    except ScopeViolation as exc:
        results["scope_blocked"] = str(exc)

    # 5) PII is redacted on sample()
    results["sample_masked"] = src.sample("customers", n=1, run_id="demo")

    # 6) every access is audited
    results["audit"] = src.audit.entries()

    _print(results)
    src.close()
    return results


def _print(r: dict[str, Any]) -> None:
    print("\nSilmari demo — governed read-only access\n" + "=" * 42)
    print(f"1. read           : {r['read_rows']}")
    print(f"2. DROP blocked   : {r.get('drop_blocked', '(not blocked!)')[:60]}")
    print(f"3. engine read-only: write rejected by engine -> {r.get('db_write_blocked')}")
    print(f"4. scope blocked  : {r.get('scope_blocked', '(not blocked!)')[:60]}")
    print(f"5. PII redacted   : {r['sample_masked']}")
    print(f"6. audit ({len(r['audit'])} rows): {[(e['kind'], e['target']) for e in r['audit']]}")
    print("=" * 42 + "\n")


def main() -> None:
    """Console entry point (``silmari-demo``); exits 0."""
    run_demo()
