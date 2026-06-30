# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Silmari runtime — manifest, registry, executor, Signal model, result store, scheduler."""

from __future__ import annotations

from .agent import AgentResult, AgentSession, ScriptedLLM
from .agent.conversation import ConversationStore
from .agent.register import BotProposal, propose_bot
from .context import BotResult, Context
from .executor import run_bot, start_run
from .manifest import BotManifest
from .prediction import prediction, prediction_result
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
from .scaffold import create_bot
from .scheduler import build_scheduler
from .signal import NOT_A_VERDICT, Signal, confidence_band, result, signal
from .sinks import EventBus, Subscription, SubscriptionStore
from .store import ResultStore, StoredRun

__version__ = "0.1.0"
__license__ = "AGPL-3.0-or-later"

# Note: the FastAPI app lives in `silmari_runtime.api` (import it from there) so that importing
# `silmari_runtime` does not eagerly pull in FastAPI.

__all__ = [
    "NOT_A_VERDICT",
    "AgentResult",
    "AgentSession",
    "BotManifest",
    "BotProposal",
    "BotRecord",
    "BotResult",
    "Context",
    "ConversationStore",
    "EventBus",
    "Proposal",
    "ProposalStore",
    "ResultStore",
    "ReviewDecision",
    "ReviewStore",
    "RulesetDoc",
    "RulesetError",
    "ScriptedLLM",
    "Signal",
    "StoredRun",
    "Subscription",
    "SubscriptionStore",
    "TuningReport",
    "ValidationReport",
    "__license__",
    "__version__",
    "build_scheduler",
    "confidence_band",
    "create_bot",
    "evaluate",
    "load_bot",
    "load_registry",
    "merge_ruleset",
    "prediction",
    "prediction_result",
    "propose_bot",
    "result",
    "run_bot",
    "run_ruleset",
    "signal",
    "start_run",
    "tuning_report",
    "validate_ruleset",
]
