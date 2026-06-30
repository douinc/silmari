import time
from pathlib import Path

from silmari_core import AuditLog, MockSource
from silmari_runtime.executor import run_bot, start_run
from silmari_runtime.registry import load_registry
from silmari_runtime.store import STATUS_COMPLETED, ResultStore

EXAMPLES = Path(__file__).resolve().parents[3] / "examples" / "bots"


def _source() -> MockSource:
    return MockSource(
        {"orders": [{"id": 1, "total": 100}, {"id": 2, "total": 50}]},
        audit=AuditLog(),
    )


def test_run_bot_end_to_end() -> None:
    record = load_registry(EXAMPLES)["example-signal"]
    store = ResultStore()
    run = run_bot(record, _source(), store, trigger="manual")

    assert run.status == STATUS_COMPLETED
    assert len(run.data) == 1  # only the order with total >= 75
    assert run.data[0]["target_id"] == "1"
    assert run.data[0]["note"]  # not-a-verdict attached

    latest = store.latest("example-signal")
    assert latest is not None
    assert latest.data == run.data


def test_start_run_daemon_thread(tmp_path) -> None:
    record = load_registry(EXAMPLES)["example-signal"]
    store = ResultStore(f"sqlite:///{tmp_path}/store.sqlite")
    running = start_run(record, _source(), store)
    assert running.status == "running"

    final = None
    for _ in range(200):
        final = store.get("example-signal", running.run_id)
        if final and final.status == STATUS_COMPLETED:
            break
        time.sleep(0.02)

    assert final is not None
    assert final.status == STATUS_COMPLETED
    assert len(final.data) == 1
