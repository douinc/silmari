# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Validate an agent-proposed pipeline against the configured source, then write ``bots/<id>/``.

Before anything is written, the proposal is validated: static checks (id/kind/tables, ``run`` is
defined, no mutating SQL literal), then a real run against the **scoped, read-only** source — so
the platform invariants (read-only, table scope, the not-a-verdict note, returns a ``BotResult``)
are enforced. Propose-only: it writes to disk for human review; it does not activate the bot.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sys
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from silmari_core import DataAccess, DataSource

from ..context import BotResult, Context
from ..signal import NOT_A_VERDICT

_BOT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_MUTATING_RE = re.compile(r"\b(insert|update|delete|drop|alter|truncate|merge)\b\s", re.IGNORECASE)
_KINDS = ("signal", "prediction")
_VALIDATE_TIMEOUT_S = 10.0


@dataclass
class BotProposal:
    bot_id: str
    pipeline_source: str
    tables: list[str]
    kind: str = "signal"
    name: str | None = None
    created_by: str = "agent"
    scope: str = ""
    as_of: str = "D-1"
    cron: str = "0 6 * * *"
    timezone: str = "UTC"


@dataclass
class ProposedBot:
    valid: bool
    bot_id: str
    path: str = ""
    record_count: int = 0
    summary: str = ""
    errors: list[str] = field(default_factory=list)


REGISTER_BOT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "register_bot",
        "description": (
            "Validate and propose a new bot. Provide a complete pipeline.py whose run(context) "
            "returns review-priority signals carrying the not-a-verdict note "
            "(use signal()/result())."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "bot_id": {"type": "string", "description": "lowercase slug"},
                "pipeline_source": {"type": "string", "description": "full pipeline.py source"},
                "tables": {"type": "array", "items": {"type": "string"}},
                "kind": {"type": "string", "enum": list(_KINDS)},
                "name": {"type": "string"},
            },
            "required": ["bot_id", "pipeline_source", "tables"],
        },
    },
}


def _static_errors(proposal: BotProposal) -> list[str]:
    errors: list[str] = []
    if not _BOT_ID_RE.fullmatch(proposal.bot_id):
        errors.append(f"bot_id {proposal.bot_id!r} must match ^[a-z0-9][a-z0-9_-]*$")
    if proposal.kind not in _KINDS:
        errors.append(f"kind must be one of {_KINDS}")
    if not proposal.tables:
        errors.append("tables must be non-empty")
    if "def run(" not in proposal.pipeline_source:
        errors.append("pipeline_source must define run(context)")
    if _MUTATING_RE.search(proposal.pipeline_source):
        errors.append("pipeline_source contains a mutating SQL keyword (read-only only)")
    return errors


def _validate_run(
    source: DataSource, proposal: BotProposal, *, timeout: float = _VALIDATE_TIMEOUT_S
) -> tuple[list[str], int, str]:
    holder: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "pipeline_under_validation.py"
        path.write_text(proposal.pipeline_source, encoding="utf-8")
        # Unique module name: two concurrent validations of the same bot_id (e.g. the demo's fixed
        # id, now reachable via HTTP) must not collide on the global sys.modules key.
        mod_name = f"silmari_validate_{proposal.bot_id}_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            return ["could not load pipeline"], 0, ""
        loader = spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module

        def _worker() -> None:
            try:
                loader.exec_module(module)  # import-time code runs here too, under the timeout
            except Exception as exc:  # noqa: BLE001
                holder["error"] = f"import error: {exc}"
                return
            run = getattr(module, "run", None)
            if not callable(run):
                holder["error"] = "pipeline has no run(context)"
                return
            scoped = source.scoped(DataAccess(tables=list(proposal.tables)), run_id="validate")
            ctx = Context(source=scoped, config={}, run_id="validate", as_of=proposal.as_of)
            try:
                holder["result"] = run(ctx)
            except PermissionError as exc:
                holder["error"] = f"read-only/scope violation: {exc}"
            except Exception as exc:  # noqa: BLE001
                holder["error"] = f"runtime error: {exc}"

        # Daemon thread: a hung proposal (incl. import-time code) can't block the timeout or process
        # exit. A thread can't be killed, so a runaway proposal leaks until exit — true isolation
        # needs a subprocess (see SECURITY.md). Validation passing is a smoke test, not a sandbox.
        thread = threading.Thread(target=_worker, name=f"validate-{proposal.bot_id}", daemon=True)
        thread.start()
        thread.join(timeout)
        sys.modules.pop(spec.name, None)
        if thread.is_alive():
            return [f"pipeline exceeded {timeout:g}s"], 0, ""

    if "error" in holder:
        return [str(holder["error"])], 0, ""
    result = holder.get("result")
    if not isinstance(result, BotResult) or not isinstance(result.data, list):
        return ["run(context) must return a BotResult whose data is a list"], 0, ""
    if result.data:
        if not all(isinstance(r, dict) and r.get("note") == NOT_A_VERDICT for r in result.data):
            return (
                ["every emitted record must carry the not-a-verdict note (use signal()/result())"],
                0,
                "",
            )
    elif NOT_A_VERDICT not in result.summary:
        return ["output is missing the not-a-verdict note (use result())"], 0, ""
    return [], len(result.data), result.summary


def _manifest_dict(proposal: BotProposal) -> dict[str, Any]:
    return {
        "bot_id": proposal.bot_id,
        "name": proposal.name or proposal.bot_id,
        "version": "0.1.0",
        "created_by": proposal.created_by,
        "created_via": "agent",
        "kind": proposal.kind,
        "trigger": {"type": "schedule", "cron": proposal.cron, "timezone": proposal.timezone},
        "data_access": {
            "tables": list(proposal.tables),
            "scope": proposal.scope,
            "as_of": proposal.as_of,
        },
        "output": {"format": "json"},
        "sinks": [{"type": "api"}],
        "audit": {"log_queries": True, "log_outputs": True},
    }


def _test_source(proposal: BotProposal) -> str:
    tables = list(proposal.tables)
    return (
        '"""Generated smoke test — expand with assertions against representative data."""\n'
        "import importlib.util\n"
        "from pathlib import Path\n\n"
        "from silmari_core import DataAccess, MockSource\n"
        "from silmari_runtime.context import BotResult, Context\n\n"
        '_PIPELINE = Path(__file__).resolve().parent.parent / "pipeline.py"\n\n\n'
        "def _load_run():\n"
        '    spec = importlib.util.spec_from_file_location("pipeline_under_test", _PIPELINE)\n'
        "    module = importlib.util.module_from_spec(spec)\n"
        "    spec.loader.exec_module(module)\n"
        "    return module.run\n\n\n"
        "def test_pipeline_runs():\n"
        f"    tables = {tables!r}\n"
        "    source = MockSource({t: [] for t in tables})\n"
        "    context = Context(\n"
        '        source=source.scoped(DataAccess(tables=tables), run_id="t"),\n'
        '        config={}, run_id="t", as_of="2024-01-01",\n'
        "    )\n"
        "    result = _load_run()(context)\n"
        "    assert isinstance(result, BotResult)\n"
    )


def _write_bot(proposal: BotProposal, bots_dir: str | Path) -> Path:
    bot_dir = Path(bots_dir) / proposal.bot_id
    if bot_dir.exists():
        shutil.rmtree(bot_dir)
    (bot_dir / "tests").mkdir(parents=True)
    (bot_dir / "manifest.yaml").write_text(
        yaml.safe_dump(_manifest_dict(proposal), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    (bot_dir / "pipeline.py").write_text(proposal.pipeline_source, encoding="utf-8")
    (bot_dir / "tests" / "test_pipeline.py").write_text(_test_source(proposal), encoding="utf-8")
    return bot_dir


def propose_bot(
    proposal: BotProposal,
    source: DataSource,
    *,
    bots_dir: str | Path = "bots",
    overwrite: bool = False,
    timeout: float = _VALIDATE_TIMEOUT_S,
) -> ProposedBot:
    errors = _static_errors(proposal)
    if errors:
        return ProposedBot(valid=False, bot_id=proposal.bot_id, errors=errors)

    bot_dir = Path(bots_dir) / proposal.bot_id
    if bot_dir.exists() and not overwrite:
        return ProposedBot(
            valid=False, bot_id=proposal.bot_id, errors=[f"{bot_dir} already exists"]
        )

    errors, count, summary = _validate_run(source, proposal, timeout=timeout)
    if errors:
        return ProposedBot(valid=False, bot_id=proposal.bot_id, errors=errors)

    written = _write_bot(proposal, bots_dir)
    return ProposedBot(
        valid=True,
        bot_id=proposal.bot_id,
        path=str(written),
        record_count=count,
        summary=summary,
    )


def dispatch_register(
    arguments: dict[str, Any], source: DataSource, *, bots_dir: str | Path = "bots"
) -> str:
    proposal = BotProposal(
        bot_id=str(arguments.get("bot_id", "")),
        pipeline_source=str(arguments.get("pipeline_source", "")),
        tables=list(arguments.get("tables", []) or []),
        kind=str(arguments.get("kind", "signal")),
        name=arguments.get("name"),
    )
    proposed = propose_bot(proposal, source, bots_dir=bots_dir)
    next_steps = (
        f"Review bots/{proposed.bot_id}/, run its tests, and commit to activate."
        if proposed.valid
        else "Fix the errors and call register_bot again."
    )
    return json.dumps(
        {
            "valid": proposed.valid,
            "bot_id": proposed.bot_id,
            "path": proposed.path,
            "record_count": proposed.record_count,
            "summary": proposed.summary,
            "errors": proposed.errors,
            "next_steps": next_steps,
        },
        ensure_ascii=False,
    )
