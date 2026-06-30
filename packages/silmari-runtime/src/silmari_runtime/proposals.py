"""Ruleset proposal flow: stage (validated) → approve (re-validate, merge, write) / reject.

A reviewer proposes a new ruleset; it is validated before staging and **re-validated at approve
time** (never trusted blindly). The live ``ruleset.json`` is written only at approve, so the
running bot picks up the change on its next run (hot-reload).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .ruleset import RulesetError, ValidationReport, merge_ruleset, validate_ruleset


@dataclass
class Proposal:
    bot_id: str
    reviewer: str
    created_at: str
    ruleset: dict[str, Any]


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ProposalStore:
    """At most one pending proposal per bot, stored as ``<directory>/<bot_id>.json``."""

    def __init__(self, directory: str | Path) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, bot_id: str) -> Path:
        return self._dir / f"{bot_id}.json"

    def stage(self, bot_id: str, ruleset: dict[str, Any], *, reviewer: str = "") -> Proposal:
        report = validate_ruleset(ruleset)
        if not report.valid:
            raise RulesetError(f"invalid ruleset: {report.errors}")
        proposal = Proposal(bot_id=bot_id, reviewer=reviewer, created_at=_now(), ruleset=ruleset)
        self._path(bot_id).write_text(
            json.dumps(
                {
                    "bot_id": bot_id,
                    "reviewer": reviewer,
                    "created_at": proposal.created_at,
                    "ruleset": ruleset,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return proposal

    def get(self, bot_id: str) -> Proposal | None:
        path = self._path(bot_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Proposal(
            bot_id=data["bot_id"],
            reviewer=data.get("reviewer", ""),
            created_at=data.get("created_at", ""),
            ruleset=data["ruleset"],
        )

    def discard(self, bot_id: str) -> bool:
        path = self._path(bot_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def approve(self, bot_id: str, ruleset_path: str | Path) -> ValidationReport:
        proposal = self.get(bot_id)
        if proposal is None:
            raise RulesetError(f"no pending proposal for {bot_id!r}")
        report = validate_ruleset(proposal.ruleset)  # re-validate; do not trust the staged blob
        if not report.valid:
            raise RulesetError(f"staged ruleset no longer valid: {report.errors}")
        live = Path(ruleset_path)
        base = json.loads(live.read_text(encoding="utf-8")) if live.exists() else {}
        merged = merge_ruleset(base, proposal.ruleset)
        live.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        self.discard(bot_id)
        return report
