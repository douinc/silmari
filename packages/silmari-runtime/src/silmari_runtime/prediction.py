# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prediction signals — the builder behind ``kind: prediction`` bots.

A prediction is a **probability in [0, 1] for a generic entity**, framed as a review-priority
signal, never a decision: :func:`prediction` requires a score, clamps it, attaches a confidence
band, and carries the not-a-verdict note by construction. The entity is generic (``target_id`` +
a free-form ``subject``) — no domain identity model is baked in. :func:`prediction_result` frames
a list of predictions into a :class:`~silmari_runtime.context.BotResult` tagged ``kind:
prediction``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .context import BotResult
from .signal import Signal, result, signal


def prediction(
    target_id: str,
    score: float,
    *,
    label: str = "prediction",
    evidence: Iterable[str] | None = None,
    features: dict[str, Any] | None = None,
    subject: dict[str, Any] | None = None,
) -> Signal:
    """A prediction signal: a probability in [0, 1] for an entity (clamped, banded, not-a-verdict).

    Unlike :func:`~silmari_runtime.signal.signal`, ``score`` is **required** — a prediction without
    a probability is meaningless.
    """
    return signal(
        target_id,
        label,
        score=float(score),
        evidence=evidence,
        features=features,
        subject=subject,
    )


def prediction_result(
    predictions: Iterable[Signal],
    *,
    label: str = "prediction",
    threshold: float | None = None,
    as_of: str = "",
    extra_metadata: dict[str, Any] | None = None,
    summary: str | None = None,
) -> BotResult:
    """Frame predictions into a BotResult tagged ``kind: prediction`` (threshold-filtered)."""
    return result(
        predictions,
        label=label,
        threshold=threshold,
        as_of=as_of,
        extra_metadata=extra_metadata,
        summary=summary,
        kind="prediction",
    )
