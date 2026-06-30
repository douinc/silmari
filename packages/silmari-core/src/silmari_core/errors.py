# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Silmari core exceptions.

Both subclass ``PermissionError`` so callers can ``except PermissionError`` for any access
violation, or catch the specific type.
"""

from __future__ import annotations


class ReadOnlyViolation(PermissionError):
    """Raised when SQL is not a single, pure, read-only SELECT statement."""


class ScopeViolation(PermissionError):
    """Raised when a query references tables outside the declared allowlist."""
