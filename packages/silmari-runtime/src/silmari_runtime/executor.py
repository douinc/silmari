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
import time
import uuid
from collections.abc import Callable
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from silmari_core import DataAccess, DataSource

from .context import BotResult, Context
from .manifest import BotManifest
from .registry import BotRecord
from .sinks import EventBus, Subscription, SubscriptionStore, deliver_webhooks
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


def _webhook_subs(
    manifest: BotManifest, subscriptions: SubscriptionStore | None
) -> list[Subscription]:
    subs = [
        Subscription(id="manifest", bot_id=manifest.bot_id, type="webhook", url=sink.url)
        for sink in manifest.sinks
        if sink.type == "webhook" and sink.url
    ]
    if subscriptions is not None:
        subs += subscriptions.list(manifest.bot_id)
    return subs


def _begin_run(
    record: BotRecord,
    source: DataSource,
    store: ResultStore,
    llm: LLMClient | None = None,
    *,
    trigger: str,
    bus: EventBus | None = None,
    subscriptions: SubscriptionStore | None = None,
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

    emit: Callable[[str, dict[str, Any] | None], None] | None = None
    if bus is not None:
        event_bus = bus

        def _emit(stage: str, detail: dict[str, Any] | None = None) -> None:
            event_bus.publish(
                {
                    "type": "run_progress",
                    "bot_id": manifest.bot_id,
                    "run_id": run_id,
                    "stage": stage,
                    **(detail or {}),
                }
            )

        emit = _emit

    context = Context(
        source=scoped,
        config={"trigger": trigger, **manifest.model_dump()},
        run_id=run_id,
        as_of=as_of,
        summarize=(llm.summarize if llm is not None else None),
        emit=emit,
    )
    running = store.create_running(manifest.bot_id, run_id, as_of)
    if bus is not None:
        bus.publish(
            {
                "type": "run_started",
                "bot_id": manifest.bot_id,
                "run_id": run_id,
                "as_of": as_of,
                "trigger": trigger,
            }
        )

    def execute() -> StoredRun:
        start = time.perf_counter()
        try:
            result = record.run(context)
            if not isinstance(result, BotResult):
                raise TypeError(
                    f"bot {manifest.bot_id!r} run() returned {type(result).__name__}, "
                    "expected BotResult"
                )
        except Exception as exc:
            store.mark_failed(run_id, f"{type(exc).__name__}: {exc}")
            if bus is not None:
                bus.publish(
                    {
                        "type": "run_failed",
                        "bot_id": manifest.bot_id,
                        "run_id": run_id,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            raise
        stored = store.mark_completed(run_id, result)
        if bus is not None:
            bus.publish(
                {
                    "type": "run_completed",
                    "bot_id": manifest.bot_id,
                    "run_id": run_id,
                    "record_count": len(stored.data),
                    "execution_ms": int((time.perf_counter() - start) * 1000),
                }
            )
        subs = _webhook_subs(manifest, subscriptions)
        if subs:
            deliver_webhooks(
                {
                    "bot_id": manifest.bot_id,
                    "run_id": run_id,
                    "as_of": as_of,
                    "summary": stored.summary,
                    "data": stored.data,
                    "metadata": stored.metadata,
                },
                subs,
            )
        return stored

    return running, execute


def run_bot(
    record: BotRecord,
    source: DataSource,
    store: ResultStore,
    llm: LLMClient | None = None,
    *,
    trigger: str = "schedule",
    bus: EventBus | None = None,
    subscriptions: SubscriptionStore | None = None,
) -> StoredRun:
    """Run a bot inline (begin + execute). Raises on pipeline failure (already recorded)."""
    _running, execute = _begin_run(
        record, source, store, llm, trigger=trigger, bus=bus, subscriptions=subscriptions
    )
    return execute()


def start_run(
    record: BotRecord,
    source: DataSource,
    store: ResultStore,
    llm: LLMClient | None = None,
    *,
    trigger: str = "manual",
    bus: EventBus | None = None,
    subscriptions: SubscriptionStore | None = None,
) -> StoredRun:
    """Begin a run, execute it on a daemon thread, and return the in-flight run immediately."""
    running, execute = _begin_run(
        record, source, store, llm, trigger=trigger, bus=bus, subscriptions=subscriptions
    )

    def _worker() -> None:
        try:
            execute()
        except Exception:
            pass  # failure already recorded on the run row

    threading.Thread(target=_worker, name=f"run-{running.run_id}", daemon=True).start()
    return running
