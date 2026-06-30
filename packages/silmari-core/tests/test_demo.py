from silmari_core.demo import run_demo


def test_demo_runs_and_enforces_all_guarantees(tmp_path) -> None:
    r = run_demo(str(tmp_path / "demo.duckdb"))

    # 1) read works
    assert r["read_rows"] == [{"id": 1, "total": 100}, {"id": 2, "total": 50}]
    # 2) parser guard blocked the DROP
    assert "drop_blocked" in r
    # 3) engine physically blocked the write (truthy = exception type name)
    assert r["db_write_blocked"]
    # 4) scope blocked the out-of-scope read
    assert "scope_blocked" in r
    # 5) PII redacted on sample
    assert r["sample_masked"][0]["email"] == "***"
    assert r["sample_masked"][0]["name"] == "***"
    # 6) accesses were audited
    assert any(e["kind"] == "query" for e in r["audit"])
