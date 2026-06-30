# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP routers. Dependencies are read from ``request.app.state`` (wired by ``create_app``)."""

from __future__ import annotations

import json
import queue
import re
import uuid
from collections.abc import Iterator
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from silmari_core import ReadOnlyViolation, ScopeViolation

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

# A generic, read-only browser over the configured DataSource: list tables, a table's schema, a
# masked sample, column stats, and an ad-hoc query — all through the DataSource read-only guard +
# audit. Masking: /sample and /stats read a *validated* table/column, so name-based masking applies
# to the real columns; /query takes arbitrary SQL, so its masking is a best-effort floor over direct
# column names only — an aliased/computed column (e.g. SELECT secret AS x) is NOT masked. The API is
# unauthenticated (see SECURITY.md) — deploy behind auth and a read-only DB role.

data_router = APIRouter(prefix="/v1/data", tags=["data"])

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _require_source(request: Request) -> Any:
    source = request.app.state.source
    if source is None:
        raise HTTPException(503, "no data source configured")
    return source


def _ident(name: str, *, dotted: bool = False) -> str:
    """Accept only a bare (optionally schema-qualified) SQL identifier.

    The table/column path params are interpolated into SQL by ``sample()``/``stats()``; validating
    them here stops a caller from smuggling a subquery (e.g. ``(SELECT secret AS x FROM t) s``) that
    would otherwise defeat the name-based masking on those endpoints.
    """
    parts = name.split(".") if dotted else [name]
    if (dotted and len(parts) > 2) or not all(_IDENT.fullmatch(p) for p in parts):
        raise HTTPException(400, f"invalid identifier: {name!r}")
    return name


@data_router.get("/tables")
def list_tables(request: Request) -> dict[str, Any]:
    return {"tables": _require_source(request).schema()}


@data_router.get("/tables/{table}")
def table_schema(table: str, request: Request) -> dict[str, Any]:
    source = _require_source(request)
    return {"table": table, "schema": source.schema(_ident(table, dotted=True))}


@data_router.get("/tables/{table}/sample")
def table_sample(table: str, request: Request, n: int = 10) -> dict[str, Any]:
    source = _require_source(request)
    rows = source.sample(_ident(table, dotted=True), max(1, min(int(n), 100)))
    return {"table": table, "rows": rows}


@data_router.get("/tables/{table}/columns/{column}/stats")
def column_stats(table: str, column: str, request: Request) -> dict[str, Any]:
    source = _require_source(request)
    rows = source.stats(_ident(table, dotted=True), _ident(column))
    return {"table": table, "column": column, "stats": rows}


class QueryRequest(BaseModel):
    sql: str


@data_router.post("/query")
def run_query(body: QueryRequest, request: Request) -> dict[str, Any]:
    source = _require_source(request)
    # Only the read-only/scope guard maps to a client error (400); a backend failure must surface as
    # a 500, not be relabelled 400 with the raw error text leaked to the caller.
    try:
        rows = [source.masking.mask(row) for row in source.query(body.sql)]
    except (ReadOnlyViolation, ScopeViolation) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"rows": rows}


# ----------------------------------------------------------------- authoring (local-only agent)

# Run the local-only authoring agent over the configured source and return a *proposed* bot
# (propose-only — written to a throwaway staging dir; nothing is activated). Gated: only active
# when an authoring_llm is configured. `serve --demo-data` wires a deterministic ScriptedLLM, so
# the demo is offline and runs *known* code; a real local model would run model-written code at
# validation time — keep it behind auth, in an isolated environment (see SECURITY.md).

authoring_router = APIRouter(prefix="/v1/authoring", tags=["authoring"])


class AuthoringRequest(BaseModel):
    message: str


@authoring_router.post("/propose")
def propose_bot_via_agent(body: AuthoringRequest, request: Request) -> dict[str, Any]:
    llm = request.app.state.authoring_llm
    if llm is None:
        raise HTTPException(503, "authoring is not enabled (no model configured)")
    source = request.app.state.source
    if source is None:
        raise HTTPException(503, "no data source configured")

    import shutil
    import tempfile

    from ..agent.harness import AgentSession

    staging = tempfile.mkdtemp(prefix="silmari-propose-")
    try:
        session = AgentSession(llm, source, authoring=True, bots_dir=staging)
        outcome = session.run(body.message)
        register = next((s for s in outcome.steps if s.tool == "register_bot"), None)
        proposal: dict[str, Any] | None = None
        if register is not None:
            data = json.loads(register.result)
            proposal = {
                "bot_id": data.get("bot_id"),
                "valid": data.get("valid"),
                "record_count": data.get("record_count"),
                "summary": data.get("summary"),
                "errors": data.get("errors") or [],
                "pipeline": register.arguments.get("pipeline_source", ""),
            }
        return {
            "final_text": outcome.final_text,
            "steps": [s.tool for s in outcome.steps],
            "proposal": proposal,
        }
    finally:
        shutil.rmtree(staging, ignore_errors=True)
