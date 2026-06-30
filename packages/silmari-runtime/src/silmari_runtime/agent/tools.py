# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Agent tools: read-only data-source exploration, plus (authoring mode) bot proposal.

Tools return JSON strings and never raise — a tool error (incl. scope/read-only violations) is
returned as ``{"error": ...}`` so the model can react.
"""

from __future__ import annotations

import json
from typing import Any

from silmari_core import DataSource

_MAX_ROWS = 50

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "data_schema",
            "description": "List tables and their columns; pass a table to scope to just one.",
            "parameters": {"type": "object", "properties": {"table": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "data_sample",
            "description": "Return up to n masked example rows from a table (default 5, max 20).",
            "parameters": {
                "type": "object",
                "properties": {"table": {"type": "string"}, "n": {"type": "integer"}},
                "required": ["table"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "data_stats",
            "description": "Top value counts for a column.",
            "parameters": {
                "type": "object",
                "properties": {"table": {"type": "string"}, "column": {"type": "string"}},
                "required": ["table", "column"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "data_query",
            "description": "Run a read-only SELECT and return rows as JSON (truncated at 50).",
            "parameters": {
                "type": "object",
                "properties": {"sql": {"type": "string"}},
                "required": ["sql"],
            },
        },
    },
]


class SourceToolbox:
    def __init__(self, source: DataSource) -> None:
        self._source = source

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return TOOL_SCHEMAS

    def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        try:
            return json.dumps(self._call(name, arguments), ensure_ascii=False, default=str)
        except PermissionError as exc:
            return json.dumps({"error": f"permission denied: {exc}"})
        except Exception as exc:  # noqa: BLE001 — tools report errors, never raise into the loop
            return json.dumps({"error": str(exc)})

    def _call(self, name: str, arguments: dict[str, Any]) -> Any:
        if name == "data_schema":
            return self._source.schema(arguments.get("table"))
        if name == "data_sample":
            return self._source.sample(arguments["table"], n=min(int(arguments.get("n", 5)), 20))
        if name == "data_stats":
            return self._source.stats(arguments["table"], arguments["column"])
        if name == "data_query":
            # Mask query results too (sample/stats already do) — an agent must not pull unmasked
            # rows into the transcript when a masking policy is configured.
            rows = [self._source.masking.mask(row) for row in self._source.query(arguments["sql"])]
            if len(rows) > _MAX_ROWS:
                return {"truncated": True, "shown": _MAX_ROWS, "rows": rows[:_MAX_ROWS]}
            return {"rows": rows}
        return {"error": f"unknown tool {name!r}"}


class AuthoringToolbox:
    """Source tools plus ``register_bot`` (validate a proposed pipeline against the source)."""

    def __init__(self, source: DataSource, *, bots_dir: str = "bots") -> None:
        self._source = source
        self._bots_dir = bots_dir
        self._tools = SourceToolbox(source)

    @property
    def schemas(self) -> list[dict[str, Any]]:
        from .register import REGISTER_BOT_TOOL

        return [*TOOL_SCHEMAS, REGISTER_BOT_TOOL]

    def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        if name == "register_bot":
            try:
                from .register import dispatch_register

                return dispatch_register(arguments, self._source, bots_dir=self._bots_dir)
            except Exception as exc:  # noqa: BLE001 — tools report errors, never raise into the loop
                return json.dumps({"error": str(exc)})
        return self._tools.dispatch(name, arguments)
