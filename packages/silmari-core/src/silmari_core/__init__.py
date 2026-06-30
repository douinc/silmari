# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Silmari core — governed, read-only, scoped, audited data access for LLM agents."""

from __future__ import annotations

from .adapters import DuckDBSource, PostgresSource, SQLiteSource, connect
from .audit import AuditLog
from .config import Settings, get_settings
from .errors import ReadOnlyViolation, ScopeViolation
from .llm import LLMClient, is_local_model
from .masking import ColumnMasking, MaskingPolicy, NoMasking, default_masking
from .mock import MockSource
from .sensitive import NoFilter, RegexFilter, SensitiveFilter
from .source import DataAccess, DataSource, ScopedSource
from .sql import assert_read_only, tables_referenced

__version__ = "0.1.0"
__license__ = "AGPL-3.0-or-later"

__all__ = [
    "AuditLog",
    "ColumnMasking",
    "DataAccess",
    "DataSource",
    "DuckDBSource",
    "LLMClient",
    "MaskingPolicy",
    "MockSource",
    "NoFilter",
    "NoMasking",
    "PostgresSource",
    "ReadOnlyViolation",
    "RegexFilter",
    "SQLiteSource",
    "ScopeViolation",
    "ScopedSource",
    "SensitiveFilter",
    "Settings",
    "__license__",
    "__version__",
    "assert_read_only",
    "connect",
    "default_masking",
    "get_settings",
    "is_local_model",
    "tables_referenced",
]
