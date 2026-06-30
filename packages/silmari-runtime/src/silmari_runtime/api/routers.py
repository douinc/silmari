# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP routers. Dependencies are read from ``request.app.state`` (wired by ``create_app``)."""

from __future__ import annotations

import json
import queue
import uuid
from collections.abc import Iterator
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..executor import start_run
from ..registry import load_registry
from ..review import build_cases, tuning_report
from ..sinks import EventBus, Subscription
from ..store import StoredRun


def _run_payload(run: StoredRun) -> dict[str, Any]:
    return {
        "bot_id": run.bot_id,
        "run_id": run.run_id,
        "as_of": run.as_of,
        "status": run.status,
        "summary": run.summary,
        "data": run.data,
        "metadata": run.metadata,
    }


# --------------------------------------------------------------------------- bots

bots_router = APIRouter(prefix="/v1/bots", tags=["bots"])


@bots_router.get("")
def list_bots(request: Request) -> list[dict[str, Any]]:
    registry = request.app.state.registry
    return [
        {"bot_id": r.manifest.bot_id, "name": r.manifest.name, "version": r.manifest.version}
        for r in registry.values()
    ]


@bots_router.get("/{bot_id}")
def get_bot(bot_id: str, request: Request) -> dict[str, Any]:
    registry = request.app.state.registry
    if bot_id not in registry:
        raise HTTPException(404, f"unknown bot {bot_id!r}")
    runs = request.app.state.store.history(bot_id, limit=10)
    return {
        "manifest": registry[bot_id].manifest.model_dump(),
        "recent_runs": [
            {"run_id": r.run_id, "as_of": r.as_of, "status": r.status, "summary": r.summary}
            for r in runs
        ],
    }


@bots_router.get("/{bot_id}/results")
def latest_results(bot_id: str, request: Request) -> dict[str, Any]:
    run = request.app.state.store.latest(bot_id)
    if run is None:
        raise HTTPException(404, f"no completed run for {bot_id!r}")
    return _run_payload(run)


@bots_router.get("/{bot_id}/results/{run_id}")
def run_results(bot_id: str, run_id: str, request: Request) -> dict[str, Any]:
    run = request.app.state.store.get(bot_id, run_id)
    if run is None:
        raise HTTPException(404, f"unknown run {run_id!r}")
    return _run_payload(run)


@bots_router.post("/{bot_id}/run", status_code=202)
def trigger_run(bot_id: str, request: Request) -> dict[str, Any]:
    registry = request.app.state.registry
    if bot_id not in registry:
        raise HTTPException(404, f"unknown bot {bot_id!r}")
    source = request.app.state.source
    if source is None:
        raise HTTPException(503, "no data source configured")
    try:
        run = start_run(
            registry[bot_id],
            source,
            request.app.state.store,
            trigger="manual",
            bus=request.app.state.bus,
            subscriptions=request.app.state.subscriptions,
        )
    except ValueError as exc:  # e.g. unscoped bot with no explicit opt-in
        raise HTTPException(400, str(exc)) from exc
    return {"bot_id": run.bot_id, "run_id": run.run_id, "as_of": run.as_of, "status": run.status}


# --------------------------------------------------------------------------- runs + SSE

runs_router = APIRouter(prefix="/v1/runs", tags=["runs"])


@runs_router.get("")
def list_runs(request: Request, limit: int = 50) -> dict[str, Any]:
    runs = request.app.state.store.recent(limit=max(1, min(limit, 200)))
    return {
        "runs": [
            {
                "bot_id": r.bot_id,
                "run_id": r.run_id,
                "as_of": r.as_of,
                "status": r.status,
                "summary": r.summary,
                "record_count": len(r.data),
                "created_at": r.created_at,
                "error": r.error,
            }
            for r in runs
        ]
    }


def sse_stream(bus: EventBus) -> Iterator[str]:
    """Server-Sent-Events generator: primes, then streams bus events (keepalive on idle)."""
    q = bus.subscribe()
    try:
        yield ": connected\n\n"
        while True:
            try:
                event = q.get(timeout=15)
            except queue.Empty:
                yield ": keepalive\n\n"
                continue
            yield f"event: {event.get('type', 'message')}\ndata: {json.dumps(event)}\n\n"
    finally:
        bus.unsubscribe(q)


@runs_router.get("/stream")
def stream_runs(request: Request) -> StreamingResponse:
    return StreamingResponse(
        sse_stream(request.app.state.bus),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------------------------------- review + tuning

review_router = APIRouter(prefix="/v1/bots", tags=["review"])


class DecisionIn(BaseModel):
    decision: str
    note: str = ""
    reviewer: str = ""


@review_router.get("/{bot_id}/runs/{run_id}/cases")
def list_cases(bot_id: str, run_id: str, request: Request) -> dict[str, Any]:
    run = request.app.state.store.get(bot_id, run_id)
    if run is None:
        raise HTTPException(404, f"unknown run {run_id!r}")
    reviews = request.app.state.reviews
    decisions = reviews.decisions_for_run(bot_id, run_id)
    cases = []
    for case_id, score, record in build_cases(run.data):
        decision = decisions.get(case_id)
        cases.append(
            {
                "case_id": case_id,
                "score": score,
                "record": record,
                "decision": decision.decision if decision else "pending",
                "note": decision.note if decision else "",
                "reviewer": decision.reviewer if decision else "",
            }
        )
    return {
        "bot_id": bot_id,
        "run_id": run_id,
        "summary": run.summary,
        "tally": reviews.tally(bot_id, run_id, total_cases=len(cases)),
        "cases": cases,
    }


@review_router.post("/{bot_id}/runs/{run_id}/cases/{case_id}/decision")
def decide(
    bot_id: str, run_id: str, case_id: str, body: DecisionIn, request: Request
) -> dict[str, Any]:
    run = request.app.state.store.get(bot_id, run_id)
    if run is None:
        raise HTTPException(404, f"unknown run {run_id!r}")
    if case_id not in {cid for cid, _score, _record in build_cases(run.data)}:
        raise HTTPException(404, f"unknown case {case_id!r} for run {run_id!r}")
    reviews = request.app.state.reviews
    try:
        decision = reviews.set_decision(
            bot_id, run_id, case_id, body.decision, note=body.note, reviewer=body.reviewer
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "case_id": case_id,
        "decision": decision.decision,
        "note": decision.note,
        "reviewer": decision.reviewer,
        "updated_at": decision.updated_at,
        "tally": reviews.tally(bot_id, run_id, total_cases=len(run.data)),
    }


@review_router.get("/{bot_id}/tuning")
def tuning(bot_id: str, request: Request) -> dict[str, Any]:
    report = tuning_report(request.app.state.store, request.app.state.reviews, bot_id)
    return asdict(report)


# --------------------------------------------------------------------------- subscriptions

subscriptions_router = APIRouter(prefix="/v1/bots/{bot_id}/subscriptions", tags=["subscriptions"])

_ALLOWED_SINK_TYPES = {"webhook", "sse", "file", "email"}


class SubscriptionIn(BaseModel):
    type: str
    url: str | None = None
    name: str | None = None


@subscriptions_router.post("")
def add_subscription(bot_id: str, body: SubscriptionIn, request: Request) -> dict[str, Any]:
    if body.type not in _ALLOWED_SINK_TYPES:
        raise HTTPException(400, f"unsupported subscription type {body.type!r}")
    if body.type == "webhook" and not (body.url and body.url.startswith(("http://", "https://"))):
        raise HTTPException(400, "a webhook subscription requires an http(s) url")
    sub = Subscription(
        id=uuid.uuid4().hex[:12], bot_id=bot_id, type=body.type, url=body.url, name=body.name
    )
    request.app.state.subscriptions.register(sub)
    return sub.__dict__


@subscriptions_router.get("")
def list_subscriptions(bot_id: str, request: Request) -> list[dict[str, Any]]:
    return [s.__dict__ for s in request.app.state.subscriptions.list(bot_id)]


@subscriptions_router.delete("/{sub_id}")
def remove_subscription(bot_id: str, sub_id: str, request: Request) -> dict[str, Any]:
    if not request.app.state.subscriptions.remove(bot_id, sub_id):
        raise HTTPException(404, f"unknown subscription {sub_id!r}")
    return {"deleted": sub_id}


# --------------------------------------------------------------------------- admin

admin_router = APIRouter(prefix="/v1/admin", tags=["admin"])


@admin_router.post("/reload-registry")
def reload_registry(request: Request) -> dict[str, Any]:
    request.app.state.registry = load_registry(request.app.state.bots_dir)
    registry = request.app.state.registry
    return {"reloaded": True, "bot_count": len(registry), "bot_ids": sorted(registry)}


# ----------------------------------------------------------------- data (read-only browser)

# A generic, read-only browser over the configured DataSource: list tables, inspect a table's
# schema, sample masked rows, column stats, and run an ad-hoc query. Everything goes through the
# DataSource's read-only guard + audit; query results are masked. The API is unauthenticated
# (see SECURITY.md) — deploy behind auth and point it at a read-only DB role.

data_router = APIRouter(prefix="/v1/data", tags=["data"])


def _require_source(request: Request) -> Any:
    source = request.app.state.source
    if source is None:
        raise HTTPException(503, "no data source configured")
    return source


@data_router.get("/tables")
def list_tables(request: Request) -> dict[str, Any]:
    return {"tables": _require_source(request).schema()}


@data_router.get("/tables/{table}")
def table_schema(table: str, request: Request) -> dict[str, Any]:
    return {"table": table, "schema": _require_source(request).schema(table)}


@data_router.get("/tables/{table}/sample")
def table_sample(table: str, request: Request, n: int = 10) -> dict[str, Any]:
    source = _require_source(request)
    try:
        rows = source.sample(table, max(1, min(int(n), 100)))
    except Exception as exc:  # noqa: BLE001 — user-supplied table → client error, audited
        raise HTTPException(400, str(exc)) from exc
    return {"table": table, "rows": rows}


@data_router.get("/tables/{table}/columns/{column}/stats")
def column_stats(table: str, column: str, request: Request) -> dict[str, Any]:
    source = _require_source(request)
    try:
        rows = source.stats(table, column)
    except Exception as exc:  # noqa: BLE001 — user-supplied table/column → client error, audited
        raise HTTPException(400, str(exc)) from exc
    return {"table": table, "column": column, "stats": rows}


class QueryRequest(BaseModel):
    sql: str


@data_router.post("/query")
def run_query(body: QueryRequest, request: Request) -> dict[str, Any]:
    source = _require_source(request)
    try:
        rows = [source.masking.mask(row) for row in source.query(body.sql)]
    except Exception as exc:  # noqa: BLE001 — read-only/scope violation or SQL error → client error
        raise HTTPException(400, str(exc)) from exc
    return {"rows": rows}
