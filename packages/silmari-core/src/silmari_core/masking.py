"""Direct-identifier masking for sampled rows.

``MaskingPolicy`` is the interface; ``NoMasking`` is the no-op default. A configurable
column-pattern policy is added in ``ColumnMasking`` (see below / later milestone).
"""

from __future__ import annotations

from typing import Any, Protocol


class MaskingPolicy(Protocol):
    def mask(self, row: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of ``row`` with direct-identifier columns redacted."""
        ...


class NoMasking:
    """Default policy: redact nothing."""

    def mask(self, row: dict[str, Any]) -> dict[str, Any]:
        return row
