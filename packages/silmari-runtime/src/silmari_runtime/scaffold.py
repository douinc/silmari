"""Scaffold a new bot (manifest + pipeline + smoke test) — the ``silmari new-bot`` generator."""

from __future__ import annotations

import re
from pathlib import Path

_BOT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_KINDS = ("signal", "prediction")

_MANIFEST = """bot_id: {bot_id}
name: {name}
version: "0.1.0"
created_by: "{created_by}"
created_via: manual
kind: {kind}

trigger:
  type: schedule
  cron: "0 6 * * *"
  timezone: UTC

data_access:
  tables:
    - your_table
  scope: ""
  as_of: D-1

output:
  format: json

sinks:
  - type: api

audit:
  log_queries: true
  log_outputs: true
"""

_PIPELINE = '''"""{name} — edit run() to read your tables and emit review-priority signals."""
from __future__ import annotations

from silmari_runtime.context import BotResult, Context
from silmari_runtime.signal import result, signal


def run(context: Context) -> BotResult:
    rows = context.source.query("SELECT * FROM your_table")
    signals = [
        signal(target_id=str(row.get("id", "")), label="{schema_ref}", evidence=[])
        for row in rows
    ]
    return result(signals, label="{schema_ref}", as_of=context.as_of)
'''

_TEST = '''"""Smoke test for {bot_id} — expand with assertions against representative data."""
import importlib.util
from pathlib import Path

from silmari_core import DataAccess, MockSource
from silmari_runtime.context import BotResult, Context

_PIPELINE = Path(__file__).resolve().parent.parent / "pipeline.py"


def _load_run():
    spec = importlib.util.spec_from_file_location("pipeline_under_test", _PIPELINE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run


def test_pipeline_runs():
    source = MockSource({{"your_table": []}})
    context = Context(
        source=source.scoped(DataAccess(tables=["your_table"]), run_id="t"),
        config={{}},
        run_id="t",
        as_of="2024-01-01",
    )
    assert isinstance(_load_run()(context), BotResult)
'''


def create_bot(
    bot_id: str,
    *,
    kind: str = "signal",
    name: str | None = None,
    created_by: str = "Developer",
    bots_dir: str | Path = "bots",
) -> Path:
    if not _BOT_ID_RE.fullmatch(bot_id):
        raise ValueError(f"bot_id {bot_id!r} must match ^[a-z0-9][a-z0-9_-]*$")
    if kind not in _KINDS:
        raise ValueError(f"kind must be one of {_KINDS}")
    bot_dir = Path(bots_dir) / bot_id
    if bot_dir.exists():
        raise FileExistsError(f"{bot_dir} already exists")

    name = name or bot_id
    schema_ref = bot_id.replace("-", "_")
    (bot_dir / "tests").mkdir(parents=True)
    (bot_dir / "manifest.yaml").write_text(
        _MANIFEST.format(bot_id=bot_id, name=name, created_by=created_by, kind=kind),
        encoding="utf-8",
    )
    (bot_dir / "pipeline.py").write_text(
        _PIPELINE.format(name=name, schema_ref=schema_ref), encoding="utf-8"
    )
    (bot_dir / "tests" / "test_pipeline.py").write_text(
        _TEST.format(bot_id=bot_id), encoding="utf-8"
    )
    return bot_dir
