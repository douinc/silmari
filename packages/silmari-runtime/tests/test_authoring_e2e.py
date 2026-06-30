"""End-to-end authoring, fully offline: a scripted local model explores the source then proposes
a bot via register_bot, which is validated against the source and written to disk.
"""

import json
from typing import Any

from silmari_core import MockSource
from silmari_runtime.agent.harness import AgentSession


class FakeLLM:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self._i = 0

    def chat(self, messages, *, model=None, tools=None) -> dict[str, Any]:
        response = self._responses[min(self._i, len(self._responses) - 1)]
        self._i += 1
        return response


def _tool_call(name: str, arguments: str) -> dict[str, Any]:
    return {
        "role": "assistant",
        "tool_calls": [{"id": "1", "function": {"name": name, "arguments": arguments}}],
    }


PIPELINE = """
from silmari_runtime.signal import result, signal


def run(context):
    rows = context.source.query("SELECT * FROM events")
    sigs = [signal(target_id=str(r["id"]), label="flag") for r in rows]
    return result(sigs, label="flag", as_of=context.as_of)
"""


def test_authoring_e2e_proposes_and_writes_a_bot(tmp_path):
    source = MockSource({"events": [{"id": 1}, {"id": 2}]})
    llm = FakeLLM(
        [
            _tool_call("data_schema", "{}"),  # explore
            _tool_call(
                "register_bot",
                json.dumps(
                    {"bot_id": "made-bot", "pipeline_source": PIPELINE, "tables": ["events"]}
                ),
            ),
            {"role": "assistant", "content": "Proposed made-bot."},
        ]
    )
    session = AgentSession(llm, source, authoring=True, bots_dir=str(tmp_path))
    result = session.run("make a bot that flags events")

    assert result.stopped_reason == "completed"
    register_step = next(s for s in result.steps if s.tool == "register_bot")
    assert json.loads(register_step.result)["valid"] is True
    assert (tmp_path / "made-bot" / "manifest.yaml").exists()
    assert (tmp_path / "made-bot" / "pipeline.py").exists()
