# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Adversarial threat-model regression tests.

These lock in *which layer blocks what*, so a future refactor cannot silently reopen a bypass:

- side-effecting / non-SELECT statements (COPY, ATTACH, INSTALL/LOAD, PRAGMA, SET, EXPORT) are
  rejected by the read-only guard, evaluated under the engine's own dialect;
- external file/function data sources (DuckDB ``read_csv``/``read_parquet``/``FROM 'file'``) pass
  the read-only guard (they are reads) but fail **closed** under table scoping.
"""

import duckdb
import pytest
from silmari_core.adapters.duckdb import DuckDBSource
from silmari_core.errors import ReadOnlyViolation
from silmari_core.source import DataAccess
from silmari_core.sql import assert_read_only


@pytest.mark.parametrize(
    "sql",
    [
        "COPY orders TO 'x.csv'",  # write to the filesystem
        "ATTACH 'other.db' AS o",  # attach another database
        "INSTALL httpfs",  # load an extension
        "LOAD httpfs",
        "PRAGMA database_list",  # inspect/alter engine state
        "SET memory_limit='1GB'",  # alter session state
        "EXPORT DATABASE 'target'",  # dump to the filesystem
    ],
)
def test_readonly_guard_rejects_duckdb_side_effects(sql: str) -> None:
    with pytest.raises(ReadOnlyViolation):
        assert_read_only(sql, dialect="duckdb")


@pytest.mark.parametrize(
    "sql",
    [
        "PRAGMA query_only=OFF",  # would disable the read-only pragma itself
        "ATTACH DATABASE 'x.db' AS y",
    ],
)
def test_readonly_guard_rejects_sqlite_side_effects(sql: str) -> None:
    with pytest.raises(ReadOnlyViolation):
        assert_read_only(sql, dialect="sqlite")


def _seed(path: str) -> None:
    con = duckdb.connect(path)
    con.execute("CREATE TABLE orders(id INTEGER)")
    con.execute("INSERT INTO orders VALUES (1)")
    con.close()


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM read_csv_auto('/etc/passwd')",
        "SELECT * FROM 'secret.parquet'",
        "SELECT * FROM read_parquet('s3://bucket/secret.parquet')",
    ],
)
def test_scope_fails_closed_for_external_file_sources(tmp_path, sql: str) -> None:
    db = str(tmp_path / "demo.duckdb")
    _seed(db)
    src = DuckDBSource(db, read_only=True)
    scoped = src.scoped(DataAccess(tables=["orders"]))
    # blocked before execution — PermissionError covers ScopeViolation and ReadOnlyViolation
    with pytest.raises(PermissionError):
        scoped.query(sql)
    src.close()


def test_duckdb_external_file_access_disabled_by_default(tmp_path) -> None:
    # Even unscoped, a read-only DuckDB source must not read arbitrary files (C1).
    db = str(tmp_path / "demo.duckdb")
    _seed(db)
    secret = tmp_path / "secret.csv"
    secret.write_text("ssn\n123-45-6789\n")
    src = DuckDBSource(db, read_only=True)
    with pytest.raises(Exception):  # noqa: B017 — duckdb raises its own permission error
        src.query(f"SELECT * FROM read_csv_auto('{secret}')")
    src.close()


def test_duckdb_external_access_is_opt_in(tmp_path) -> None:
    db = str(tmp_path / "demo.duckdb")
    _seed(db)
    data = tmp_path / "data.csv"
    data.write_text("v\n1\n")
    src = DuckDBSource(db, read_only=True, allow_external_access=True)
    assert src.query(f"SELECT * FROM read_csv_auto('{data}')") == [{"v": 1}]
    src.close()
