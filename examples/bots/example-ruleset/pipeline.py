# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Example declarative bot — all logic lives in ``ruleset.json`` (no per-bot Python).

The pipeline just loads and runs the ruleset; editing ``ruleset.json`` changes behavior with no
code change (and is picked up on the next run).
"""

from __future__ import annotations

from pathlib import Path

from silmari_runtime.context import BotResult, Context
from silmari_runtime.ruleset import run_ruleset

_RULESET = Path(__file__).resolve().parent / "ruleset.json"


def run(context: Context) -> BotResult:
    return run_ruleset(context, _RULESET)
