# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sensitive-data redaction applied before any non-local model call.

``SensitiveFilter`` is the interface. ``RegexFilter`` is an always-on, network-free floor for
common direct identifiers; ``NoFilter`` is a passthrough. Plug in a stronger model-based filter
(e.g. a model-based NER redactor) by implementing the ``SensitiveFilter`` protocol.
"""

from __future__ import annotations

import re
from typing import Protocol


class SensitiveFilter(Protocol):
    def redact(self, text: str) -> str:
        """Return ``text`` with detected direct identifiers replaced by placeholders."""
        ...


class NoFilter:
    """Passthrough — redacts nothing."""

    def redact(self, text: str) -> str:
        return text


_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    (re.compile(r"\b(?:\d[ -]?){13,16}\b"), "[CARD]"),
]


class RegexFilter:
    """Deterministic regex floor for common direct identifiers (email, SSN, card numbers)."""

    def redact(self, text: str) -> str:
        for pattern, replacement in _PATTERNS:
            text = pattern.sub(replacement, text)
        return text
