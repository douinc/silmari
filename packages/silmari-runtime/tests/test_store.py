# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
from silmari_runtime.context import BotResult
from silmari_runtime.store import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_RUNNING,
    ResultStore,
)


def test_lifecycle_completed() -> None:
    store = ResultStore()
    run = store.create_running("bot", "run1", "2024-01-01")
    assert run.status == STATUS_RUNNING

    botresult = BotResult(data=[{"x": 1}], metadata={"k": "v"}, summary="s")
    done = store.mark_completed("run1", botresult)
    assert done.status == STATUS_COMPLETED
    assert done.data == [{"x": 1}]
    assert done.metadata == {"k": "v"}
    assert done.summary == "s"

    got = store.get("bot", "run1")
    assert got is not None
    assert got.data == [{"x": 1}]


def test_lifecycle_failed() -> None:
    store = ResultStore()
    store.create_running("bot", "run2", "")
    failed = store.mark_failed("run2", "boom")
    assert failed.status == STATUS_FAILED
    assert failed.error == "boom"


def test_latest_and_history() -> None:
    store = ResultStore()
    for i in range(3):
        rid = f"r{i}"
        store.create_running("bot", rid, "")
        store.mark_completed(rid, BotResult(data=[], metadata={}, summary=f"s{i}"))

    history = store.history("bot")
    assert len(history) == 3
    latest = store.latest("bot")
    assert latest is not None
    assert latest.summary == "s2"


def test_get_wrong_bot_returns_none() -> None:
    store = ResultStore()
    store.create_running("bot", "r", "")
    assert store.get("other", "r") is None
