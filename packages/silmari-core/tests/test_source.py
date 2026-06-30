import pytest
from silmari_core.audit import AuditLog
from silmari_core.errors import ReadOnlyViolation, ScopeViolation
from silmari_core.mock import MockSource
from silmari_core.source import DataAccess


def make() -> MockSource:
    return MockSource(
        {
            "demo.orders": [{"id": 1, "total": 100}, {"id": 2, "total": 50}],
            "demo.secret": [{"id": 9, "ssn": "x"}],
        },
        audit=AuditLog(),
    )


# ------------------------------------------------------------------- query + audit


def test_query_returns_rows_and_audits() -> None:
    src = make()
    rows = src.query("SELECT * FROM demo.orders", run_id="r1")
    assert len(rows) == 2
    last = src.audit.entries()[-1]
    assert last["kind"] == "query"
    assert last["target"] == "demo.orders"
    assert last["row_count"] == 2
    assert last["run_id"] == "r1"


def test_query_rejects_write() -> None:
    with pytest.raises(ReadOnlyViolation):
        make().query("DELETE FROM demo.orders")


def test_query_limit() -> None:
    assert len(make().query("SELECT * FROM demo.orders LIMIT 1")) == 1


def test_sample_returns_rows() -> None:
    assert len(make().sample("demo.orders", n=1)) == 1


def test_schema_audited() -> None:
    src = make()
    src.schema("demo.orders")
    assert src.audit.entries()[-1]["kind"] == "schema"


# ------------------------------------------------------------------- scoping


def test_scoped_allows_declared_table() -> None:
    scoped = make().scoped(DataAccess(tables=["demo.orders"]), run_id="r1")
    assert len(scoped.query("SELECT * FROM demo.orders")) == 2


def test_scoped_blocks_undeclared_table() -> None:
    scoped = make().scoped(DataAccess(tables=["demo.orders"]))
    with pytest.raises(ScopeViolation):
        scoped.query("SELECT * FROM demo.secret")


def test_scoped_blocks_comment_bypass() -> None:
    # `demo.secret` is the real read; `demo.orders` only appears in a comment → still blocked.
    scoped = make().scoped(DataAccess(tables=["demo.orders"]))
    with pytest.raises(ScopeViolation):
        scoped.query("/* demo.orders */ SELECT * FROM demo.secret")


def test_scoped_join_requires_all_tables() -> None:
    scoped = make().scoped(DataAccess(tables=["demo.orders"]))
    with pytest.raises(ScopeViolation):
        scoped.query("SELECT * FROM demo.orders JOIN demo.secret ON 1 = 1")


def test_scoped_empty_allowlist_is_unscoped() -> None:
    scoped = make().scoped(DataAccess(tables=[]))
    assert len(scoped.query("SELECT * FROM demo.secret")) == 1


def test_scoped_strict_bare_does_not_match_qualified() -> None:
    # No cross-schema widening: a bare scope entry does not admit a schema-qualified read.
    scoped = make().scoped(DataAccess(tables=["orders"]))
    with pytest.raises(ScopeViolation):
        scoped.query("SELECT * FROM demo.orders")


def test_scoped_bare_matches_bare() -> None:
    scoped = make().scoped(DataAccess(tables=["orders"]))
    assert len(scoped.query("SELECT * FROM orders")) == 2


def test_scoped_qualified_blocks_other_schema_same_name() -> None:
    scoped = make().scoped(DataAccess(tables=["demo.orders"]))
    with pytest.raises(ScopeViolation):
        scoped.query("SELECT * FROM evil.orders")


# ------------------------------------------------------------------- audit outcomes


def test_successful_query_outcome_ok() -> None:
    src = make()
    src.query("SELECT * FROM demo.orders")
    assert src.audit.entries()[-1]["outcome"] == "ok"


def test_readonly_denial_is_audited() -> None:
    src = make()
    with pytest.raises(ReadOnlyViolation):
        src.query("DELETE FROM demo.orders")
    assert src.audit.entries()[-1]["outcome"] == "denied"


def test_scope_denial_is_audited() -> None:
    src = make()
    scoped = src.scoped(DataAccess(tables=["demo.orders"]), run_id="r1")
    with pytest.raises(ScopeViolation):
        scoped.query("SELECT * FROM demo.secret")
    last = src.audit.entries()[-1]
    assert last["outcome"] == "denied"
    assert last["target"] == "demo.secret"


# ------------------------------------------------------------------- stats masking


def test_stats_masks_sensitive_column() -> None:
    from silmari_core.masking import ColumnMasking

    src = MockSource(
        {"t": [{"email": "a@x"}, {"email": "b@x"}]},
        audit=AuditLog(),
        masking=ColumnMasking(["email"]),
    )
    assert all(row["email"] == "***" for row in src.stats("t", "email"))
