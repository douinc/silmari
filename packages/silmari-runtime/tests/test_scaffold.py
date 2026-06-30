# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from silmari_core import MockSource
from silmari_runtime.executor import run_bot
from silmari_runtime.registry import load_bot
from silmari_runtime.scaffold import create_bot
from silmari_runtime.store import ResultStore


def test_create_bot_writes_files(tmp_path):
    path = create_bot("my-new-bot", bots_dir=tmp_path)
    assert (path / "manifest.yaml").exists()
    assert (path / "pipeline.py").exists()
    assert (path / "tests" / "test_pipeline.py").exists()


def test_create_bot_bad_id(tmp_path):
    with pytest.raises(ValueError):
        create_bot("Bad Id", bots_dir=tmp_path)


def test_create_bot_already_exists(tmp_path):
    create_bot("dup", bots_dir=tmp_path)
    with pytest.raises(FileExistsError):
        create_bot("dup", bots_dir=tmp_path)


def test_scaffolded_bot_loads_and_runs(tmp_path):
    create_bot("gen-bot", bots_dir=tmp_path)
    record = load_bot(tmp_path / "gen-bot")
    run = run_bot(record, MockSource({"your_table": []}), ResultStore(), trigger="manual")
    assert run.status == "completed"  # the scaffold output is immediately runnable
