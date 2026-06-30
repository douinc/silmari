"""Execute a bot: build a scoped source + Context, run the pipeline, persist the result.

Begin/execute split: ``_begin_run`` synchronously reserves a run row and builds the context;
the returned ``execute`` runs the pipeline and marks the run completed/failed. ``run_bot`` runs
both inline (raises on pipeline failure, after recording it); ``start_run`` runs ``execute`` on a
daemon thread and returns the in-flight run immediately.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from datetime import date, timedelta
from typing import TYPE_CHECKING

from silmari_core import DataAccess, DataSource

from .context import Context
from .registry import BotRecord
from .store import ResultStore, StoredRun

if TYPE_CHECKING:
    from silmari_core import LLMClient


def _resolve_as_of(as_of: str) -> str:
    if as_of == "D-1":
        return (date.today() - timedelta(days=1)).isoformat()
    if as_of in ("", "D", "D-0", "today"):
        return date.today().isoformat()
    return as_of


def _new_run_id() -> str:
    return f"run_{date.today():%Y%m%d}_{uuid.uuid4().hex[:8]}"


def _begin_run(
    record: BotRecord,
    source: DataSource,
    store: ResultStore,
    llm: LLMClient | None = None,
    *,
    trigger: str,
) -> tuple[StoredRun, Callable[[], StoredRun]]:
    manifest = record.manifest
    run_id = _new_run_id()
    as_of = _resolve_as_of(manifest.data_access.as_of)
    scoped = source.scoped(DataAccess(tables=list(manifest.data_access.tables)), run_id=run_id)
    context = Context(
        source=scoped,
        config={"trigger": trigger, **manifest.model_dump()},
        run_id=run_id,
        as_of=as_of,
        summarize=(llm.summarize if llm is not None else None),
    )
    running = store.create_running(manifest.bot_id, run_id, as_of)

    def execute() -> StoredRun:
        try:
            result = record.run(context)
        except Exception as exc:
            store.mark_failed(run_id, f"{type(exc).__name__}: {exc}")
            raise
        return store.mark_completed(run_id, result)

    return running, execute


def run_bot(
    record: BotRecord,
    source: DataSource,
    store: ResultStore,
    llm: LLMClient | None = None,
    *,
    trigger: str = "schedule",
) -> StoredRun:
    """Run a bot inline (begin + execute). Raises on pipeline failure (already recorded)."""
    _running, execute = _begin_run(record, source, store, llm, trigger=trigger)
    return execute()


def start_run(
    record: BotRecord,
    source: DataSource,
    store: ResultStore,
    llm: LLMClient | None = None,
    *,
    trigger: str = "manual",
) -> StoredRun:
    """Begin a run, execute it on a daemon thread, and return the in-flight run immediately."""
    running, execute = _begin_run(record, source, store, llm, trigger=trigger)

    def _worker() -> None:
        try:
            execute()
        except Exception:
            pass  # failure already recorded on the run row

    threading.Thread(target=_worker, name=f"run-{running.run_id}", daemon=True).start()
    return running
