"""LLM client (via a LiteLLM-compatible proxy) with a local-first redaction gate.

Only ``local/*`` models are exempt from redaction. For any other model, **every string** in
every message — plain ``content``, list content blocks (text/tool-result), and ``tool_calls``
arguments — is passed through the sensitive-data filter before the HTTP call, so no string-shaped
PII can leave with a non-local request regardless of message shape.
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import Settings
from .sensitive import NoFilter, RegexFilter, SensitiveFilter


def is_local_model(model: str) -> bool:
    """A model is local (and exempt from redaction) iff its name starts with ``local/``."""
    return model.startswith("local/")


class LLMClient:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        sensitive_filter: SensitiveFilter | None = None,
    ) -> None:
        self.settings = settings or Settings()
        if sensitive_filter is not None:
            self._filter: SensitiveFilter = sensitive_filter
        elif self.settings.sensitive_filter_enabled:
            self._filter = RegexFilter()
        else:
            self._filter = NoFilter()

    def _redact(self, value: Any) -> Any:
        """Recursively redact every string in a message structure (fail-safe for any shape)."""
        if isinstance(value, str):
            return self._filter.redact(value)
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        if isinstance(value, dict):
            return {key: self._redact(item) for key, item in value.items()}
        return value

    def _redact_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self._redact(message) for message in messages]

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        model = model or self.settings.llm_default_model
        sent = messages if is_local_model(model) else self._redact_messages(messages)
        payload: dict[str, Any] = {"model": model, "messages": sent}
        if tools:
            payload["tools"] = tools
        headers: dict[str, str] = {}
        if self.settings.litellm_api_key:
            headers["Authorization"] = f"Bearer {self.settings.litellm_api_key}"
        resp = httpx.post(
            f"{self.settings.litellm_base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=120,
        )
        resp.raise_for_status()
        message: dict[str, Any] = resp.json()["choices"][0]["message"]
        return message

    def summarize(self, text: str) -> str:
        message = self.chat(
            [{"role": "user", "content": f"Summarize in one line:\n\n{text}"}],
            model=self.settings.llm_summary_model,
        )
        return message.get("content") or ""
