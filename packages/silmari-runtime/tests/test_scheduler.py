# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

from silmari_core import MockSource
from silmari_runtime.registry import load_registry
from silmari_runtime.scheduler import build_scheduler
from silmari_runtime.store import ResultStore

EXAMPLES = Path(__file__).resolve().parents[3] / "examples" / "bots"


def test_build_scheduler_registers_cron_job() -> None:
    registry = load_registry(EXAMPLES)
    scheduler = build_scheduler(registry, MockSource({"orders": []}), ResultStore())
    scheduler.start(paused=True)  # flush pending jobs without firing them
    try:
        assert scheduler.get_job("example-signal") is not None
    finally:
        scheduler.shutdown(wait=False)
