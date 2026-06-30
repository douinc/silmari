# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Local-only tool-use agent loop.

The loop sends the conversation + tool schemas to a chat model, executes any tool calls, feeds the
results back, and repeats until the model answers with no tool call (or ``max_steps`` is hit). It
refuses any model not named ``local/*`` — a naming convention, not a transport guarantee (see
SECURITY.md): a ``local/*`` model is trusted to run on-prem, so the (possibly sensitive) row data
the tools return stays inside the boundary. Do not register a remote model under a ``local/`` name.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from silmari_core import DataSource, is_local_model

from .tools import AuthoringToolbox, SourceToolbox

_DEFAULT_SYSTEM = (
    "You are a data analyst. Use the tools to explore the read-only data source and answer the "
    "user's question. Cite the tables/columns you used."
)
_AUTHORING_SYSTEM = (
    "You help author a Silmari bot. Explore the read-only data source with the tools, then call "
    "register_bot with a complete pipeline.py whose run(context) returns review-priority signals "
    "(never verdicts)."
)


class ChatLLM(Protocol):
    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]: ...


@dataclass
class AgentStep:
    tool: str
    arguments: dict[str, Any]
    result: str


@dataclass
class AgentResult:
    final_text: str
    steps: list[AgentStep] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    stopped_reason: str = "completed"


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


class AgentSession:
    def __init__(
        self,
        llm: ChatLLM,
        source: DataSource,
        *,
        model: str = "local/default",
        system: str | None = None,
        max_steps: int = 8,
        authoring: bool = False,
        bots_dir: str = "bots",
    ) -> None:
        if not is_local_model(model):
            raise ValueError(
                f"agent requires a local/* model (got {model!r}); a non-local model would receive "
                "source rows returned by the tools"
            )
        self.llm = llm
        self.model = model
        self.max_steps = max_steps
        self.toolbox: AuthoringToolbox | SourceToolbox = (
            AuthoringToolbox(source, bots_dir=bots_dir) if authoring else SourceToolbox(source)
        )
        self.system = system or (_AUTHORING_SYSTEM if authoring else _DEFAULT_SYSTEM)

    def run(self, task: str) -> AgentResult:
        return self._collect(
            [{"role": "system", "content": self.system}, {"role": "user", "content": task}]
        )

    def resume(self, history: list[dict[str, Any]], user_text: str) -> AgentResult:
        messages = [
            {"role": "system", "content": self.system},
            *history,
            {"role": "user", "content": user_text},
        ]
        return self._collect(messages)

    def iter_events(
        self, history: list[dict[str, Any]], user_text: str
    ) -> Iterator[dict[str, Any]]:
        messages = [
            {"role": "system", "content": self.system},
            *history,
            {"role": "user", "content": user_text},
        ]
        yield from self._iter(messages)

    def _collect(self, messages: list[dict[str, Any]]) -> AgentResult:
        result = AgentResult(final_text="", stopped_reason="max_steps")
        for event in self._iter(messages):
            if event["type"] == "final":
                result = event["result"]
        return result

    def _iter(self, messages: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        steps: list[AgentStep] = []
        for _ in range(self.max_steps):
            message = self.llm.chat(messages, model=self.model, tools=self.toolbox.schemas)
            messages.append(message)
            tool_calls = message.get("tool_calls") or []

            if not tool_calls:
                final_text = message.get("content") or ""
                yield {"type": "assistant", "text": final_text}
                yield {
                    "type": "final",
                    "result": AgentResult(
                        final_text=final_text,
                        steps=steps,
                        messages=messages,
                        stopped_reason="completed",
                    ),
                }
                return

            for call in tool_calls:
                fn = call.get("function", {})
                name = fn.get("name", "")
                arguments = _parse_arguments(fn.get("arguments"))
                yield {"type": "tool_call", "name": name, "arguments": arguments}
                result = self.toolbox.dispatch(name, arguments)
                steps.append(AgentStep(tool=name, arguments=arguments, result=result))
                yield {"type": "tool_result", "name": name, "result": result}
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", name),
                        "name": name,
                        "content": result,
                    }
                )

        yield {
            "type": "final",
            "result": AgentResult(
                final_text="", steps=steps, messages=messages, stopped_reason="max_steps"
            ),
        }
