"""Silmari core — governed, read-only, scoped, audited data access for LLM agents."""

from __future__ import annotations

from .adapters import DuckDBSource, SQLiteSource, connect
from .audit import AuditLog
from .errors import ReadOnlyViolation, ScopeViolation
from .masking import ColumnMasking, MaskingPolicy, NoMasking, default_masking
from .mock import MockSource
from .source import DataAccess, DataSource, ScopedSource
from .sql import assert_read_only, tables_referenced

__version__ = "0.1.0"

__all__ = [
    "AuditLog",
    "ColumnMasking",
    "DataAccess",
    "DataSource",
    "DuckDBSource",
    "MaskingPolicy",
    "MockSource",
    "NoMasking",
    "ReadOnlyViolation",
    "SQLiteSource",
    "ScopeViolation",
    "ScopedSource",
    "__version__",
    "assert_read_only",
    "connect",
    "default_masking",
    "tables_referenced",
]
