# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Silmari runtime HTTP API (FastAPI)."""

from __future__ import annotations

from .app import app, create_app

__all__ = ["app", "create_app"]
