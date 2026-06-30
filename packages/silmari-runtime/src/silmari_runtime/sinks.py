"""Delivery: an in-process event bus (drives SSE) and webhook subscriptions.

The bus is thread-safe pub/sub with bounded per-subscriber queues — a slow or dead subscriber
drops events rather than blocking producers (run execution must never stall on delivery).
"""

from __future__ import annotations

import logging
import os
import queue
import re
import threading
from dataclasses import dataclass
from typing import Any

import httpx

_log = logging.getLogger(__name__)


class EventBus:
    """In-process pub/sub. Each subscriber gets its own bounded queue; full queues drop events."""

    def __init__(self, maxsize: int = 1000) -> None:
        self._subscribers: set[queue.Queue[dict[str, Any]]] = set()
        self._lock = threading.Lock()
        self._maxsize = maxsize

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=self._maxsize)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def publish(self, event: dict[str, Any]) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(event)
            except queue.Full:
                _log.warning("event queue full; dropping %s event", event.get("type", "?"))


@dataclass
class Subscription:
    id: str
    bot_id: str
    type: str  # webhook | sse | file | email
    url: str | None = None
    name: str | None = None


class SubscriptionStore:
    """In-memory subscription registry, keyed by bot_id."""

    def __init__(self) -> None:
        self._subs: dict[str, list[Subscription]] = {}
        self._lock = threading.Lock()

    def register(self, sub: Subscription) -> Subscription:
        with self._lock:
            self._subs.setdefault(sub.bot_id, []).append(sub)
        return sub

    def list(self, bot_id: str) -> list[Subscription]:
        with self._lock:
            return list(self._subs.get(bot_id, []))

    def remove(self, bot_id: str, sub_id: str) -> bool:
        with self._lock:
            subs = self._subs.get(bot_id, [])
            for i, sub in enumerate(subs):
                if sub.id == sub_id:
                    subs.pop(i)
                    return True
        return False


_ENV_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _resolve(url: str) -> str:
    """Expand ``${ENV_VAR}`` placeholders in a webhook URL (secrets stay out of the manifest)."""
    return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), ""), url)


def deliver_webhooks(payload: dict[str, Any], subscriptions: list[Subscription]) -> None:
    """POST ``payload`` to each webhook subscription. Errors are logged, never raised."""
    for sub in subscriptions:
        if sub.type != "webhook" or not sub.url:
            continue
        try:
            httpx.post(_resolve(sub.url), json=payload, timeout=15)
        except httpx.HTTPError as exc:
            _log.warning("webhook delivery to %s failed: %s", sub.name or sub.id, exc)
