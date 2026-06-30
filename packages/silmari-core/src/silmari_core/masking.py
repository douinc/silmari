# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Direct-identifier masking for sampled rows.

``MaskingPolicy`` is the interface; ``NoMasking`` is the no-op default. ``ColumnMasking`` redacts
a **configurable** set of column names — generalizing the old hardcoded identifier list so the
caller declares which columns are sensitive (no domain assumptions baked in).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

# Generic, domain-neutral PII column names you can opt into via ``default_masking()``.
COMMON_PII_COLUMNS: frozenset[str] = frozenset(
    {
        "name",
        "first_name",
        "last_name",
        "full_name",
        "email",
        "phone",
        "phone_number",
        "ssn",
        "national_id",
        "address",
        "street",
        "zip",
        "zipcode",
        "postal_code",
        "dob",
        "birth_date",
        "date_of_birth",
    }
)


class MaskingPolicy(Protocol):
    def mask(self, row: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of ``row`` with direct-identifier columns redacted."""
        ...


class NoMasking:
    """Default policy: redact nothing."""

    def mask(self, row: dict[str, Any]) -> dict[str, Any]:
        return row


class ColumnMasking:
    """Redact values whose column name is in the configured set."""

    def __init__(
        self,
        columns: Iterable[str],
        *,
        mask: str = "***",
        case_insensitive: bool = True,
    ) -> None:
        self._mask = mask
        self._case_insensitive = case_insensitive
        self._columns = {c.lower() if case_insensitive else c for c in columns}

    def mask(self, row: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in row.items():
            lookup = key.lower() if self._case_insensitive else key
            out[key] = self._mask if lookup in self._columns else value
        return out


def default_masking(mask: str = "***") -> ColumnMasking:
    """A ``ColumnMasking`` over :data:`COMMON_PII_COLUMNS` (opt-in convenience)."""
    return ColumnMasking(COMMON_PII_COLUMNS, mask=mask)
