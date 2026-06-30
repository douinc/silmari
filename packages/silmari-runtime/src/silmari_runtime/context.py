"""The runtime handle a bot pipeline receives.

A bot author writes ``def run(context: Context) -> BotResult``. The platform fills ``Context``
with a **scoped, audited** data source (so the bot can only read its declared tables) and reads
``BotResult.data`` for downstream delivery.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from silmari_core import ScopedSource


@dataclass
class Context:
    source: ScopedSource
    """Read-only, table-scoped, audited data source for this bot."""
    config: dict[str, Any]
    """Parameters from the manifest."""
    run_id: str
    as_of: str = ""
    """Data-as-of marker, e.g. an ISO date for a D-1 run."""
    summarize: Callable[[str], str] | None = None
    """Optional local-LLM one-line summarizer."""
    emit: Callable[[str, dict[str, Any] | None], None] | None = None
    """Optional progress hook: ``emit(stage, detail)``."""


@dataclass
class BotResult:
    data: list[dict[str, Any]]
    """The emitted records (signals), framed as review-priority signals — never verdicts."""
    metadata: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
