from typing import Any

import pytest
from silmari_core import MockSource
from silmari_runtime.agent.harness import AgentSession


class FakeLLM:
    """Returns canned assistant messages in order (scripts the model, fully offline)."""

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


def test_local_only_guard_rejects_non_local_model():
    with pytest.raises(ValueError, match="local/"):
        AgentSession(FakeLLM([]), MockSource({}), model="openai/gpt-4")


def test_agent_explores_then_answers():
    source = MockSource({"orders": [{"id": 1, "total": 100}]})
    llm = FakeLLM(
        [
            _tool_call("data_query", '{"sql": "SELECT * FROM orders"}'),
            {"role": "assistant", "content": "There is 1 order."},
        ]
    )
    result = AgentSession(llm, source).run("how many orders?")
    assert result.stopped_reason == "completed"
    assert result.final_text == "There is 1 order."
    assert result.steps[0].tool == "data_query"
    assert "total" in result.steps[0].result  # the row data came back to the model


def test_tool_error_is_returned_not_raised():
    source = MockSource({"orders": [{"id": 1}]})
    llm = FakeLLM(
        [
            _tool_call("data_query", '{"sql": "DELETE FROM orders"}'),  # write -> rejected
            {"role": "assistant", "content": "done"},
        ]
    )
    result = AgentSession(llm, source).run("try a write")
    assert "error" in result.steps[0].result  # ReadOnlyViolation surfaced as a tool error


def test_max_steps_stops_the_loop():
    source = MockSource({"orders": []})
    llm = FakeLLM([_tool_call("data_schema", "{}")])  # always a tool call -> never terminates
    result = AgentSession(llm, source, max_steps=3).run("loop forever")
    assert result.stopped_reason == "max_steps"
    assert len(result.steps) == 3
