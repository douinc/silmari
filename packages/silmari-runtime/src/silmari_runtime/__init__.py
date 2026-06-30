"""Silmari runtime — manifest, registry, executor, Signal model, result store, scheduler."""

from __future__ import annotations

from .context import BotResult, Context
from .executor import run_bot, start_run
from .manifest import BotManifest
from .proposals import Proposal, ProposalStore
from .registry import BotRecord, load_bot, load_registry
from .review import ReviewDecision, ReviewStore, TuningReport, tuning_report
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
from .sinks import EventBus, Subscription, SubscriptionStore
from .store import ResultStore, StoredRun

__version__ = "0.1.0"

# Note: the FastAPI app lives in `silmari_runtime.api` (import it from there) so that importing
# `silmari_runtime` does not eagerly pull in FastAPI.

__all__ = [
    "NOT_A_VERDICT",
    "BotManifest",
    "BotRecord",
    "BotResult",
    "Context",
    "EventBus",
    "Proposal",
    "ProposalStore",
    "ResultStore",
    "ReviewDecision",
    "ReviewStore",
    "RulesetDoc",
    "RulesetError",
    "Signal",
    "StoredRun",
    "Subscription",
    "SubscriptionStore",
    "TuningReport",
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
    "tuning_report",
    "validate_ruleset",
]
