# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Built-in DataSource adapters and the ``connect()`` factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .duckdb import DuckDBSource
from .sqlite import SQLiteSource

if TYPE_CHECKING:
    from ..audit import AuditLog
    from ..masking import MaskingPolicy
    from ..source import DataSource

__all__ = ["DuckDBSource", "SQLiteSource", "connect"]


def _path(url: str, scheme: str) -> str:
    rest = url[len(scheme) :]
    if rest in ("", ":memory:"):
        return ":memory:"
    if rest.startswith("//"):  # absolute, e.g. duckdb:////abs/path -> /abs/path
        return rest[1:]
    return rest.lstrip("/") or ":memory:"  # relative, e.g. duckdb:///rel.db -> rel.db


def connect(
    url: str,
    *,
    read_only: bool = True,
    audit: AuditLog | None = None,
    masking: MaskingPolicy | None = None,
) -> DataSource:
    """Open a read-only data source from a URL.

    Supported schemes: ``duckdb://`` and ``sqlite://`` (e.g. ``duckdb:///demo.db``,
    ``sqlite:///demo.sqlite``, ``duckdb://`` for in-memory).
    """
    if url.startswith("duckdb://"):
        return DuckDBSource(
            _path(url, "duckdb://"), read_only=read_only, audit=audit, masking=masking
        )
    if url.startswith("sqlite://"):
        return SQLiteSource(
            _path(url, "sqlite://"), read_only=read_only, audit=audit, masking=masking
        )
    raise ValueError(f"unsupported data source URL scheme: {url!r}")
