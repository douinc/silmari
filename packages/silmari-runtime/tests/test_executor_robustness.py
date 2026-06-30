"""Robustness regressions for the executor (review fixes): runs never stick in `running`, bot
output is type-checked, unscoped bots are flagged, and the store is safe under the daemon path.
"""

import time
from datetime import date
from pathlib import Path

import pytest
from silmari_core import AuditLog, MockSource
from silmari_runtime.context import BotResult
from silmari_runtime.executor import run_bot, start_run
from silmari_runtime.manifest import BotManifest
from silmari_runtime.registry import BotRecord, load_registry
from silmari_runtime.store import STATUS_COMPLETED, STATUS_FAILED, ResultStore

EXAMPLES = Path(__file__).resolve().parents[3] / "examples" / "bots"


def _record(run, *, tables=("orders",), unscoped=False, bot_id="syn") -> BotRecord:
    manifest = BotManifest.model_validate(
        {
            "bot_id": bot_id,
            "name": bot_id,
            "data_access": {"tables": list(tables), "unscoped": unscoped},
        }
    )
    return BotRecord(manifest=manifest, run=run, path=Path("."))


def _src() -> MockSource:
    return MockSource({"orders": [{"id": 1, "total": 100}]}, audit=AuditLog())


def test_non_botresult_return_marks_failed_not_stuck() -> None:
    store = ResultStore()
    with pytest.raises(TypeError):
        run_bot(_record(lambda ctx: "oops"), _src(), store)
    runs = store.history("syn")
    assert runs and runs[0].status == STATUS_FAILED
    assert "expected BotResult" in runs[0].error


def test_date_result_serializes_and_completes() -> None:
    # A bot returning a date must persist (as ISO) and complete — not fail or stick in "running".
    store = ResultStore()
    run = run_bot(_record(lambda ctx: BotResult(data=[{"when": date(2024, 1, 1)}])), _src(), store)
    assert run.status == STATUS_COMPLETED
    assert run.data == [{"when": "2024-01-01"}]


def test_unscoped_without_optin_is_rejected() -> None:
    # Fail closed: no declared tables and no explicit opt-in -> the run is refused.
    with pytest.raises(ValueError, match="unscoped"):
        run_bot(_record(lambda ctx: BotResult(data=[]), tables=()), _src(), ResultStore())


def test_unscoped_with_optin_runs_and_warns(caplog) -> None:
    with caplog.at_level("WARNING"):
        run = run_bot(
            _record(lambda ctx: BotResult(data=[]), tables=(), unscoped=True),
            _src(),
            ResultStore(),
        )
    assert run.status == STATUS_COMPLETED
    assert any("UNSCOPED" in r.message for r in caplog.records)


def test_start_run_with_inmemory_store_is_threadsafe() -> None:
    record = load_registry(EXAMPLES)["example-signal"]
    store = ResultStore()  # in-memory, single shared connection
    running = start_run(record, _src(), store)
    final = None
    for _ in range(200):
        final = store.get("example-signal", running.run_id)  # main reads while daemon writes
        if final and final.status == STATUS_COMPLETED:
            break
        time.sleep(0.02)
    assert final is not None and final.status == STATUS_COMPLETED
