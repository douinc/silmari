"""Bot manifest schema (pydantic). Loaded from ``bots/<id>/manifest.yaml``.

Declares the bot's read scope (``data_access.tables`` — the Executor scopes the bot to exactly
those tables), trigger, output, sinks, and audit settings. Domain-neutral defaults.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Trigger(BaseModel):
    type: Literal["schedule", "manual"] = "schedule"
    cron: str | None = None
    timezone: str = "UTC"


class DataAccessSpec(BaseModel):
    tables: list[str] = Field(default_factory=list)
    scope: str = ""
    as_of: str = "D-1"


class Output(BaseModel):
    format: Literal["json", "csv"] = "json"
    schema_ref: str | None = None


class Sink(BaseModel):
    type: Literal["api", "webhook", "sse", "file", "email"]
    url: str | None = None
    template: str | None = None
    name: str | None = None


class Audit(BaseModel):
    log_queries: bool = True
    log_outputs: bool = True


class BotManifest(BaseModel):
    bot_id: str
    name: str
    version: str = "0.1.0"
    created_by: str | None = None
    created_via: Literal["agent", "manual"] = "manual"
    kind: Literal["signal", "prediction"] = "signal"
    trigger: Trigger = Field(default_factory=Trigger)
    data_access: DataAccessSpec = Field(default_factory=DataAccessSpec)
    output: Output = Field(default_factory=Output)
    sinks: list[Sink] = Field(default_factory=list)
    audit: Audit = Field(default_factory=Audit)
