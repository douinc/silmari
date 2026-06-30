# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
from silmari_core.audit import AuditLog


def test_record_and_entries() -> None:
    audit = AuditLog()  # shared in-memory
    audit.record("query", run_id="r1", target="demo.orders", row_count=3, duration_ms=5)
    audit.record("schema", target="demo")

    rows = audit.entries()
    assert len(rows) == 2

    first = rows[0]
    assert first["kind"] == "query"
    assert first["run_id"] == "r1"
    assert first["target"] == "demo.orders"
    assert first["row_count"] == 3
    assert first["duration_ms"] == 5
    assert first["ts"]  # timestamp populated

    assert rows[1]["kind"] == "schema"
    assert rows[1]["run_id"] == ""  # default


def test_record_defaults() -> None:
    audit = AuditLog()
    audit.record("query")
    (row,) = audit.entries()
    assert row["target"] == ""
    assert row["row_count"] == 0
    assert row["duration_ms"] == 0


def test_file_backed(tmp_path) -> None:
    url = f"sqlite:///{tmp_path}/audit.sqlite"
    audit = AuditLog(url)
    audit.record("query", target="t")
    # a fresh handle to the same file sees the row (durable)
    assert AuditLog(url).entries()[0]["target"] == "t"


def test_outcome_default_ok() -> None:
    audit = AuditLog()
    audit.record("query")
    assert audit.entries()[-1]["outcome"] == "ok"


def test_outcome_recorded() -> None:
    audit = AuditLog()
    audit.record("query", outcome="denied")
    assert audit.entries()[-1]["outcome"] == "denied"
