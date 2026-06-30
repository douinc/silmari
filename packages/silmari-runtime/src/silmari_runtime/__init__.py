"""Silmari runtime — manifest, registry, executor, Signal model, result store, scheduler."""

from __future__ import annotations

from .context import BotResult, Context
from .executor import run_bot, start_run
from .manifest import BotManifest
from .registry import BotRecord, load_bot, load_registry
from .scheduler import build_scheduler
from .signal import NOT_A_VERDICT, Signal, confidence_band, result, signal
from .store import ResultStore, StoredRun

__version__ = "0.1.0"

__all__ = [
    "NOT_A_VERDICT",
    "BotManifest",
    "BotRecord",
    "BotResult",
    "Context",
    "ResultStore",
    "Signal",
    "StoredRun",
    "__version__",
    "build_scheduler",
    "confidence_band",
    "load_bot",
    "load_registry",
    "result",
    "run_bot",
    "signal",
    "start_run",
]
