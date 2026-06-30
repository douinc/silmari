# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A deterministic, offline stand-in "model" for the authoring demo (``silmari serve --demo-data``).

It is **not** a real LLM. Unlike a fixed :class:`~silmari_runtime.agent.scripted.ScriptedLLM` — which
is stateful and is exhausted after one run — this inspects the conversation on **every** turn, so it
works on every request, and it **routes the user's ask** (by keyword) to one of a few example bots
over the seeded demo tables (``orders`` / ``metrics``). The flow it plays — explore the schema,
sample the table, then propose a validated pipeline — mirrors a real agent. Wire a real ``local/*``
model for a genuinely live agent.
"""

from __future__ import annotations

from typing import Any

from .scripted import say, tool_call

_HIGH_VALUE = """from silmari_runtime.signal import result, signal


def run(context):
    rows = context.source.query("SELECT id, total FROM orders")
    flagged = [
        signal(target_id=str(r["id"]), label="high_value", score=min(1.0, r["total"] / 100))
        for r in rows
        if r["total"] >= 75
    ]
    return result(flagged, label="high_value", as_of=context.as_of)
"""

_TIMEOUTS = """from silmari_runtime.signal import result, signal


def run(context):
    rows = context.source.query("SELECT host, status_text FROM metrics")
    flagged = [
        signal(target_id=str(r["host"]), label="status_timeout", score=0.6,
               evidence=[str(r.get("status_text", ""))])
        for r in rows
        if "timeout" in str(r.get("status_text", "")).lower()
    ]
    return result(flagged, label="status_timeout", as_of=context.as_of)
"""

_HIGH_CPU = """from silmari_runtime.signal import result, signal


def run(context):
    rows = context.source.query("SELECT host, cpu FROM metrics")
    flagged = [
        signal(target_id=str(r["host"]), label="high_cpu", score=min(1.0, r["cpu"] / 100))
        for r in rows
        if r["cpu"] > 90
    ]
    return result(flagged, label="high_cpu", as_of=context.as_of)
"""

# (keywords, proposal) — first keyword match wins; otherwise the default.
_ROUTES: list[tuple[tuple[str, ...], dict[str, Any]]] = [
    (
        ("timeout", "error", "status", "fail"),
        {"bot_id": "status-timeouts", "tables": ["metrics"], "pipeline_source": _TIMEOUTS},
    ),
    (
        ("cpu", "load", "saturat"),
        {"bot_id": "high-cpu-hosts", "tables": ["metrics"], "pipeline_source": _HIGH_CPU},
    ),
]
_DEFAULT: dict[str, Any] = {
    "bot_id": "high-value-orders",
    "tables": ["orders"],
    "pipeline_source": _HIGH_VALUE,
}


def _route(message: str) -> dict[str, Any]:
    text = message.lower()
    for keywords, proposal in _ROUTES:
        if any(k in text for k in keywords):
            return proposal
    return _DEFAULT


class DemoAuthoringLLM:
    """Deterministic, stateless demo "model" (see module docstring). Not a real LLM."""

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        used = [m.get("name") for m in messages if m.get("role") == "tool"]
        if "register_bot" in used:
            return say("Proposed — review the pipeline, then register it to activate.")
        if "data_schema" not in used:
            return tool_call("data_schema")
        user = next((str(m.get("content", "")) for m in messages if m.get("role") == "user"), "")
        proposal = _route(user)
        if "data_query" not in used:
            return tool_call("data_query", sql=f"SELECT * FROM {proposal['tables'][0]} LIMIT 5")
        return tool_call("register_bot", **proposal)
