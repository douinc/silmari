# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from silmari_core.errors import ReadOnlyViolation
from silmari_core.sql import assert_read_only, tables_referenced

# ---------------------------------------------------------------- assert_read_only: allowed


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "SELECT * FROM demo.orders",
        "SELECT o.id FROM demo.orders o WHERE o.total > 100",
        "SELECT a.id FROM demo.a JOIN demo.b ON a.id = b.a_id",
        "WITH t AS (SELECT * FROM demo.orders) SELECT * FROM t",
        "SELECT * FROM demo.a UNION SELECT * FROM demo.b",
        "SELECT * FROM (SELECT id FROM demo.orders) s",
    ],
)
def test_allows_read_only(sql: str) -> None:
    assert_read_only(sql)  # must not raise


# ---------------------------------------------------------------- assert_read_only: rejected


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO demo.orders (id) VALUES (1)",
        "UPDATE demo.orders SET total = 0",
        "DELETE FROM demo.orders",
        "DROP TABLE demo.orders",
        "CREATE TABLE demo.x (id INT)",
        "ALTER TABLE demo.orders ADD COLUMN x INT",
        "TRUNCATE TABLE demo.orders",
        # write/DDL nested in a subquery or CTE
        "SELECT * FROM (DELETE FROM demo.orders RETURNING id) s",
        "WITH w AS (INSERT INTO demo.orders (id) VALUES (1) RETURNING id) SELECT * FROM w",
        # multiple statements
        "SELECT 1; DROP TABLE demo.orders",
        # empty
        "   ",
    ],
)
def test_rejects_writes(sql: str) -> None:
    with pytest.raises(ReadOnlyViolation):
        assert_read_only(sql)


def test_violation_is_permissionerror() -> None:
    with pytest.raises(PermissionError):
        assert_read_only("DROP TABLE demo.orders")


# ---------------------------------------------------------------- tables_referenced


def test_tables_basic() -> None:
    assert tables_referenced("SELECT * FROM demo.orders") == {"demo.orders"}


def test_tables_join() -> None:
    assert tables_referenced(
        "SELECT * FROM demo.a JOIN demo.b ON a.id = b.a_id"
    ) == {"demo.a", "demo.b"}


def test_tables_alias_uses_base_name() -> None:
    assert tables_referenced("SELECT * FROM demo.orders o WHERE o.id = 1") == {"demo.orders"}


def test_tables_excludes_cte() -> None:
    # `t` is a CTE alias, not a real table — only the real table is reported.
    assert tables_referenced(
        "WITH t AS (SELECT * FROM demo.orders) SELECT * FROM t"
    ) == {"demo.orders"}


def test_tables_ignores_comment_and_string() -> None:
    # Parse-based: a table name that appears only in a comment or string literal is NOT a read.
    sql = "SELECT 'demo.secret' AS s /* demo.secret */ FROM demo.orders"
    assert tables_referenced(sql) == {"demo.orders"}
