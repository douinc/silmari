from typing import Any

import silmari_core.llm as llm_mod
from silmari_core.config import Settings
from silmari_core.llm import LLMClient, is_local_model


def test_is_local_model() -> None:
    assert is_local_model("local/qwen")
    assert not is_local_model("openai/gpt-4")


class _FakeResp:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, Any]:
        return {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}


def _capture_post(captured: dict[str, Any]):
    def fake_post(url: str, **kwargs: Any) -> _FakeResp:
        captured["url"] = url
        captured["json"] = kwargs["json"]
        captured["headers"] = kwargs.get("headers", {})
        return _FakeResp()

    return fake_post


def test_chat_redacts_for_non_local_model(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(llm_mod.httpx, "post", _capture_post(captured))
    client = LLMClient(Settings())
    client.chat([{"role": "user", "content": "email a@b.com please"}], model="openai/gpt-4")
    sent = captured["json"]["messages"][0]["content"]
    assert "[EMAIL]" in sent
    assert "a@b.com" not in sent


def test_chat_does_not_redact_for_local_model(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(llm_mod.httpx, "post", _capture_post(captured))
    client = LLMClient(Settings())
    client.chat([{"role": "user", "content": "email a@b.com please"}], model="local/qwen")
    assert "a@b.com" in captured["json"]["messages"][0]["content"]


def test_chat_returns_assistant_message(monkeypatch) -> None:
    monkeypatch.setattr(llm_mod.httpx, "post", _capture_post({}))
    msg = LLMClient(Settings()).chat([{"role": "user", "content": "hi"}], model="local/x")
    assert msg == {"role": "assistant", "content": "ok"}
