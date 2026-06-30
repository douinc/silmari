# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
import sqlite3

import duckdb
import pytest
from silmari_core import DataAccess, ReadOnlyViolation, connect
from silmari_core.adapters.duckdb import DuckDBSource
from silmari_core.adapters.sqlite import SQLiteSource


def _seed_duckdb(path: str) -> None:
    con = duckdb.connect(path)
    con.execute("CREATE TABLE orders(id INTEGER, total INTEGER)")
    con.execute("INSERT INTO orders VALUES (1, 100), (2, 50)")
    con.close()


def _seed_sqlite(path: str) -> None:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE orders(id INTEGER, total INTEGER)")
    con.executemany("INSERT INTO orders VALUES (?, ?)", [(1, 100), (2, 50)])
    con.commit()
    con.close()


# ------------------------------------------------------------------- DuckDB


def test_duckdb_reads(tmp_path) -> None:
    db = str(tmp_path / "demo.duckdb")
    _seed_duckdb(db)
    src = DuckDBSource(db, read_only=True)
    assert src.query("SELECT id FROM orders ORDER BY id") == [{"id": 1}, {"id": 2}]
    src.close()


def test_duckdb_db_level_readonly(tmp_path) -> None:
    db = str(tmp_path / "demo.duckdb")
    _seed_duckdb(db)
    src = DuckDBSource(db, read_only=True)
    # 1) the parser guard rejects writes before they reach the engine
    with pytest.raises(ReadOnlyViolation):
        src.query("INSERT INTO orders VALUES (3, 1)")
    # 2) and the engine itself rejects writes even if the guard were bypassed
    with pytest.raises(Exception):  # noqa: B017 — duckdb raises its own exception type
        src._con.execute("INSERT INTO orders VALUES (3, 1)")
    src.close()


def test_duckdb_stats(tmp_path) -> None:
    db = str(tmp_path / "demo.duckdb")
    _seed_duckdb(db)
    src = DuckDBSource(db, read_only=True)
    rows = src.stats("orders", "total")
    assert {r["total"]: r["n"] for r in rows} == {100: 1, 50: 1}
    src.close()


# ------------------------------------------------------------------- SQLite


def test_sqlite_reads(tmp_path) -> None:
    db = str(tmp_path / "demo.sqlite")
    _seed_sqlite(db)
    src = SQLiteSource(db, read_only=True)
    assert src.query("SELECT id FROM orders ORDER BY id") == [{"id": 1}, {"id": 2}]
    src.close()


def test_sqlite_db_level_readonly(tmp_path) -> None:
    db = str(tmp_path / "demo.sqlite")
    _seed_sqlite(db)
    src = SQLiteSource(db, read_only=True)
    with pytest.raises(ReadOnlyViolation):
        src.query("DELETE FROM orders")
    with pytest.raises(sqlite3.Error):
        src._con.execute("INSERT INTO orders VALUES (3, 1)")
    src.close()


# ------------------------------------------------------------------- connect()


def test_connect_dispatch_and_scope(tmp_path) -> None:
    db = str(tmp_path / "demo.duckdb")
    _seed_duckdb(db)
    src = connect(f"duckdb:///{db}")
    assert len(src.query("SELECT * FROM orders")) == 2
    scoped = src.scoped(DataAccess(tables=["orders"]))
    assert len(scoped.query("SELECT * FROM orders")) == 2
    src.close()


def test_connect_unknown_scheme() -> None:
    with pytest.raises(ValueError):
        connect("mysql://nope")
