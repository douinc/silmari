# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

from silmari_runtime.registry import load_bot, load_registry

EXAMPLES = Path(__file__).resolve().parents[3] / "examples" / "bots"


def test_load_registry_finds_example() -> None:
    reg = load_registry(EXAMPLES)
    assert "example-signal" in reg
    record = reg["example-signal"]
    assert record.manifest.kind == "signal"
    assert record.manifest.data_access.tables == ["orders"]
    assert callable(record.run)


def test_load_bot_has_run() -> None:
    record = load_bot(EXAMPLES / "example-signal")
    assert callable(record.run)


def _write_bot(parent: Path, bot_id: str, body: str) -> Path:
    bot = parent / bot_id
    bot.mkdir(parents=True)
    (bot / "manifest.yaml").write_text(
        f"bot_id: {bot_id}\nname: {bot_id}\nkind: signal\ndata_access:\n  tables: [orders]\n"
    )
    (bot / "pipeline.py").write_text(body)
    return bot


def test_one_broken_bot_does_not_break_registry(tmp_path) -> None:
    _write_bot(tmp_path, "good", "def run(context):\n    return None\n")
    _write_bot(tmp_path, "broken", "raise RuntimeError('boom')\n")
    reg = load_registry(tmp_path)
    assert "good" in reg
    assert "broken" not in reg  # quarantined, not fatal


def test_bot_id_collision_yields_distinct_modules(tmp_path) -> None:
    _write_bot(tmp_path, "a-b", "def run(context):\n    return None\n")
    _write_bot(tmp_path, "a_b", "def run(context):\n    return None\n")
    reg = load_registry(tmp_path)
    assert {"a-b", "a_b"} <= set(reg)
    assert reg["a-b"].run.__module__ != reg["a_b"].run.__module__
