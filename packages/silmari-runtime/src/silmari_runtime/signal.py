# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Signal (실마리) records — the review-priority output of a bot.

A Signal is framed as a **review-priority signal, never a verdict**: every record carries the
``note`` (:data:`NOT_A_VERDICT`) so downstream consumers and reviewers see it is a lead for a
human to judge, not a decision. ``target_id`` is the opaque id of the entity scored, and
``subject`` is a free-form identity/attribute block (generic entity — the caller decides what
goes in it).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

from .context import BotResult

NOT_A_VERDICT = "Review-priority signal, not a verdict — a human reviewer decides."


def confidence_band(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.6:
        return "medium-high"
    if score >= 0.4:
        return "medium"
    return "low"


@dataclass
class Signal:
    target_id: str
    label: str
    score: float | None = None
    confidence: str = ""
    evidence: list[str] = field(default_factory=list)
    features: dict[str, Any] = field(default_factory=dict)
    subject: dict[str, Any] = field(default_factory=dict)
    note: str = NOT_A_VERDICT

    def as_record(self) -> dict[str, Any]:
        return asdict(self)


def signal(
    target_id: str,
    label: str,
    *,
    score: float | None = None,
    evidence: Iterable[str] | None = None,
    features: dict[str, Any] | None = None,
    subject: dict[str, Any] | None = None,
) -> Signal:
    """Build a Signal. If ``score`` is given it is clamped to [0, 1] and a confidence band added."""
    confidence = ""
    if score is not None:
        score = round(min(1.0, max(0.0, float(score))), 3)
        confidence = confidence_band(score)
    return Signal(
        target_id=target_id,
        label=label,
        score=score,
        confidence=confidence,
        evidence=list(evidence or []),
        features=dict(features or {}),
        subject=dict(subject or {}),
    )


def result(
    signals: Iterable[Signal],
    *,
    label: str,
    threshold: float | None = None,
    as_of: str = "",
    logic: dict[str, Any] | None = None,
    extra_metadata: dict[str, Any] | None = None,
    summary: str | None = None,
    kind: str = "signal",
) -> BotResult:
    """Frame a list of Signals into a BotResult (filter by threshold, sort desc, attach note)."""
    all_signals = list(signals)
    flagged = all_signals
    if threshold is not None:
        flagged = [s for s in all_signals if (s.score or 0.0) >= threshold]
    flagged = sorted(flagged, key=lambda s: (s.score or 0.0), reverse=True)

    metadata: dict[str, Any] = {
        "label": label,
        "cohort_size": len(all_signals),
        "flagged": len(flagged),
        "kind": kind,
    }
    if threshold is not None:
        metadata["threshold"] = threshold
    if logic:
        metadata["logic"] = logic
    if extra_metadata:
        metadata.update(extra_metadata)

    if summary is None:
        noun = "prediction" if kind == "prediction" else "signal"
        summary = f"{label}: {len(flagged)} {noun}(s) (as of {as_of or 'n/a'}; {NOT_A_VERDICT})"

    return BotResult(data=[s.as_record() for s in flagged], metadata=metadata, summary=summary)
