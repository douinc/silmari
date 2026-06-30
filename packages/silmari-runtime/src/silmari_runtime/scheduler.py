# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""APScheduler wrapper: schedule each bot's cron trigger to ``run_bot``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from silmari_core import DataSource

from .executor import run_bot
from .registry import BotRecord
from .store import ResultStore

if TYPE_CHECKING:
    from silmari_core import LLMClient


def build_scheduler(
    registry: dict[str, BotRecord],
    source: DataSource,
    store: ResultStore,
    llm: LLMClient | None = None,
    *,
    timezone: str = "UTC",
) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=timezone)
    for bot_id, record in registry.items():
        trig = record.manifest.trigger
        if trig.type == "schedule" and trig.cron:
            scheduler.add_job(
                run_bot,
                CronTrigger.from_crontab(trig.cron, timezone=trig.timezone),
                args=[record, source, store, llm],
                id=bot_id,
                replace_existing=True,
            )
    return scheduler
