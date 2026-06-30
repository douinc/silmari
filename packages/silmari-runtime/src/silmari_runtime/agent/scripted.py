# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""ScriptedLLM — a deterministic :class:`~silmari_runtime.agent.harness.ChatLLM`.

For demos and tests **without a real model**: replays a fixed list of assistant turns (optionally
carrying ``tool_calls``). The agent loop calls :meth:`chat` repeatedly; ScriptedLLM returns the next
turn, repeating the last once the script is exhausted. Because the turns are fixed, the pipeline the
agent ends up proposing is fixed too — so running the authoring loop against a ScriptedLLM executes
*known* code, which is what makes the authoring demo safe to expose (a real model would emit
arbitrary code; see SECURITY.md). Build turns with :func:`tool_call` / :func:`say`.
"""

from __future__ import annotations

import json
from typing import Any


def tool_call(name: str, **arguments: Any) -> dict[str, Any]:
    """An assistant turn that invokes one tool with the given JSON arguments."""
    return {
        "role": "assistant",
        "tool_calls": [
            {"id": name, "function": {"name": name, "arguments": json.dumps(arguments)}}
        ],
    }


def say(text: str) -> dict[str, Any]:
    """A final assistant turn with no tool call — ends the loop."""
    return {"role": "assistant", "content": text}


class ScriptedLLM:
    def __init__(self, turns: list[dict[str, Any]]) -> None:
        if not turns:
            raise ValueError("ScriptedLLM needs at least one turn")
        self._turns = list(turns)
        self._i = 0

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        turn = self._turns[min(self._i, len(self._turns) - 1)]
        self._i += 1
        return turn
