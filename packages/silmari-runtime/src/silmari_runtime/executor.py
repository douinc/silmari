"""Execute a bot: build a scoped source + Context, run the pipeline, persist the result.

Begin/execute split: ``_begin_run`` synchronously reserves a run row and builds the context;
the returned ``execute`` runs the pipeline and marks the run completed/failed. ``run_bot`` runs
both inline (raises on pipeline failure, after recording it); ``start_run`` runs ``execute`` on a
daemon thread and returns the in-flight run immediately.
"""

from __future__ import annotations

import logging
import re
import threading
import uuid
from collections.abc import Callable
from datetime import date, timedelta
from typing import TYPE_CHECKING

from silmari_core import DataAccess, DataSource

from .context import BotResult, Context
from .registry import BotRecord
from .store import ResultStore, StoredRun

if TYPE_CHECKING:
    from silmari_core import LLMClient

_log = logging.getLogger(__name__)


_RELATIVE_AS_OF = re.compile(r"^D-(\d+)$")


def _resolve_as_of(as_of: str) -> str:
    if as_of in ("", "D", "D-0", "today"):
        return date.today().isoformat()
    match = _RELATIVE_AS_OF.match(as_of)
    if match:
        return (date.today() - timedelta(days=int(match.group(1)))).isoformat()
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
    tables = list(manifest.data_access.tables)
    if not tables and not manifest.data_access.unscoped:
        raise ValueError(
            f"bot {manifest.bot_id!r} declares no data_access.tables; set "
            "data_access.unscoped: true to explicitly allow full read access"
        )
    if not tables:
        _log.warning(
            "bot %r running UNSCOPED (data_access.unscoped) — full read access", manifest.bot_id
        )
    scoped = source.scoped(DataAccess(tables=tables), run_id=run_id)
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
            if not isinstance(result, BotResult):
                raise TypeError(
                    f"bot {manifest.bot_id!r} run() returned {type(result).__name__}, "
                    "expected BotResult"
                )
            return store.mark_completed(run_id, result)
        except Exception as exc:
            store.mark_failed(run_id, f"{type(exc).__name__}: {exc}")
            raise

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
