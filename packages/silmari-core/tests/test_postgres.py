# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Offline tests for the Postgres adapter — no live database.

The psycopg interaction sits behind a single seam (`postgres._connect`), so most tests fake the
connection; one test fakes the `psycopg` module itself to verify the real read-only wiring.
"""

import sys

import pytest
from silmari_core import PostgresSource, ReadOnlyViolation, connect
from silmari_core.adapters import postgres as pg


class FakeCursor:
    def __init__(self, description, rows, calls):
        self._description = description
        self._rows = rows
        self._calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def description(self):
        return self._description

    def execute(self, sql, params=None):
        self._calls.append((sql, params))

    def fetchall(self):
        return self._rows


class FakeConn:
    def __init__(self, description=None, rows=()):
        self._description = description
        self._rows = list(rows)
        self.calls = []
        self.closed = False

    def cursor(self):
        return FakeCursor(self._description, self._rows, self.calls)

    def close(self):
        self.closed = True


def _source(monkeypatch, *, description=None, rows=()):
    conn = FakeConn(description, rows)
    monkeypatch.setattr(pg, "_connect", lambda dsn, *, read_only=True: conn)
    return PostgresSource("postgresql://u@h/db"), conn


def test_connect_dispatches_postgres(monkeypatch):
    monkeypatch.setattr(pg, "_connect", lambda dsn, *, read_only=True: FakeConn())
    src = connect("postgresql://u@h/db")
    assert isinstance(src, PostgresSource)
    assert src._dialect == "postgres"


def test_query_returns_dicts_and_audits(monkeypatch):
    src, conn = _source(monkeypatch, description=[("id",), ("total",)], rows=[(1, 100), (2, 50)])
    rows = src.query("SELECT id, total FROM orders")
    assert rows == [{"id": 1, "total": 100}, {"id": 2, "total": 50}]
    assert src.audit.entries()[-1]["outcome"] == "ok"


def test_rejects_writes_before_touching_the_cursor(monkeypatch):
    src, conn = _source(monkeypatch)
    with pytest.raises(ReadOnlyViolation):
        src.query("UPDATE orders SET total = 0")
    assert conn.calls == []  # the SQL guard fired before any cursor execution


def test_schema_lists_tables(monkeypatch):
    src, _ = _source(monkeypatch, rows=[("metrics",), ("orders",)])
    assert src.schema() == ["metrics", "orders"]


def test_schema_for_one_qualified_table(monkeypatch):
    src, conn = _source(monkeypatch, rows=[("id", "integer"), ("total", "integer")])
    assert src.schema("public.orders") == {
        "public.orders": [
            {"column": "id", "type": "integer"},
            {"column": "total", "type": "integer"},
        ]
    }
    # qualified name is split into schema + table for the information_schema lookup
    assert conn.calls[0][1] == ("public", "orders")


def test_connect_sets_session_read_only(monkeypatch):
    statements: list[str] = []
    captured: dict = {}

    class _Conn:
        def execute(self, sql, *a):
            statements.append(sql)

    class _Psycopg:
        @staticmethod
        def connect(dsn, autocommit=False):
            captured.update(dsn=dsn, autocommit=autocommit)
            return _Conn()

    monkeypatch.setitem(sys.modules, "psycopg", _Psycopg)

    pg._connect("postgresql://h/db", read_only=True)
    assert captured["autocommit"] is True
    assert any("default_transaction_read_only = on" in s for s in statements)

    statements.clear()
    pg._connect("postgresql://h/db", read_only=False)
    assert statements == []  # read_only=False must not force the session setting
