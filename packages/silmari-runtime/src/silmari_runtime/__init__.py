"""Silmari runtime — manifest, registry, executor, Signal model, result store, scheduler."""

from __future__ import annotations

from .context import BotResult, Context
from .executor import run_bot, start_run
from .manifest import BotManifest
from .proposals import Proposal, ProposalStore
from .registry import BotRecord, load_bot, load_registry
from .ruleset import (
    RulesetDoc,
    RulesetError,
    ValidationReport,
    evaluate,
    merge_ruleset,
    run_ruleset,
    validate_ruleset,
)
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
    "Proposal",
    "ProposalStore",
    "ResultStore",
    "RulesetDoc",
    "RulesetError",
    "Signal",
    "StoredRun",
    "ValidationReport",
    "__version__",
    "build_scheduler",
    "confidence_band",
    "evaluate",
    "load_bot",
    "load_registry",
    "merge_ruleset",
    "result",
    "run_bot",
    "run_ruleset",
    "signal",
    "start_run",
    "validate_ruleset",
]
