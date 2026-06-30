# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
import json

from silmari_core import MockSource
from silmari_runtime.agent.register import BotProposal, dispatch_register, propose_bot
from silmari_runtime.agent.tools import AuthoringToolbox
from silmari_runtime.signal import NOT_A_VERDICT

VALID_PIPELINE = """
from silmari_runtime.context import BotResult, Context
from silmari_runtime.signal import result, signal


def run(context):
    rows = context.source.query("SELECT * FROM events")
    sigs = [signal(target_id=str(r["id"]), label="flag", evidence=[]) for r in rows]
    return result(sigs, label="flag", as_of=context.as_of)
"""


def test_propose_valid_bot_writes_files(tmp_path):
    source = MockSource({"events": [{"id": 1}, {"id": 2}]})
    proposed = propose_bot(
        BotProposal(bot_id="my-bot", pipeline_source=VALID_PIPELINE, tables=["events"]),
        source,
        bots_dir=tmp_path,
    )
    assert proposed.valid
    assert proposed.record_count == 2
    assert (tmp_path / "my-bot" / "manifest.yaml").exists()
    assert (tmp_path / "my-bot" / "pipeline.py").exists()
    assert (tmp_path / "my-bot" / "tests" / "test_pipeline.py").exists()


def test_propose_rejects_bad_bot_id(tmp_path):
    proposed = propose_bot(
        BotProposal(bot_id="Bad Id", pipeline_source="def run(context): pass", tables=["t"]),
        MockSource({}),
        bots_dir=tmp_path,
    )
    assert not proposed.valid


def test_propose_rejects_mutating_sql(tmp_path):
    bad = "def run(context):\n    context.source.query('DELETE FROM events')\n"
    proposed = propose_bot(
        BotProposal(bot_id="b", pipeline_source=bad, tables=["events"]),
        MockSource({"events": []}),
        bots_dir=tmp_path,
    )
    assert not proposed.valid
    assert any("mutating" in e.lower() for e in proposed.errors)


def test_propose_rejects_missing_not_a_verdict_note(tmp_path):
    bad = (
        "from silmari_runtime.context import BotResult\n"
        "def run(context):\n"
        "    return BotResult(data=[{'x': 1}], summary='no note here')\n"
    )
    proposed = propose_bot(
        BotProposal(bot_id="b", pipeline_source=bad, tables=["events"]),
        MockSource({"events": [{"id": 1}]}),
        bots_dir=tmp_path,
    )
    assert not proposed.valid
    assert any("not-a-verdict" in e for e in proposed.errors)


def test_propose_rejects_out_of_scope_read(tmp_path):
    bad = (
        "from silmari_runtime.signal import result\n"
        "def run(context):\n"
        "    context.source.query('SELECT * FROM secret')\n"
        "    return result([], label='x', as_of=context.as_of)\n"
    )
    source = MockSource({"events": [{"id": 1}], "secret": [{"id": 9}]})
    proposed = propose_bot(
        BotProposal(bot_id="b", pipeline_source=bad, tables=["events"]),
        source,
        bots_dir=tmp_path,
    )
    assert not proposed.valid
    assert any("scope" in e.lower() or "violation" in e.lower() for e in proposed.errors)


def test_dispatch_register_returns_json(tmp_path):
    source = MockSource({"events": [{"id": 1}]})
    out = json.loads(
        dispatch_register(
            {"bot_id": "d-bot", "pipeline_source": VALID_PIPELINE, "tables": ["events"]},
            source,
            bots_dir=tmp_path,
        )
    )
    assert out["valid"] is True
    assert out["bot_id"] == "d-bot"
    assert "next_steps" in out


def test_propose_times_out_on_a_hanging_pipeline(tmp_path):
    import time

    hang = "import time\ndef run(context):\n    time.sleep(30)\n"
    start = time.perf_counter()
    proposed = propose_bot(
        BotProposal(bot_id="hang", pipeline_source=hang, tables=["events"]),
        MockSource({"events": []}),
        bots_dir=tmp_path,
        timeout=0.3,
    )
    elapsed = time.perf_counter() - start
    assert not proposed.valid
    assert any("exceeded" in e for e in proposed.errors)
    assert elapsed < 5  # the timeout bounded the call; it did not block on the hung thread


def test_propose_times_out_on_import_time_hang(tmp_path):
    import time

    # module-level (import-time) hang must also be bounded by the timeout
    hang = "import time\ntime.sleep(30)\ndef run(context):\n    pass\n"
    start = time.perf_counter()
    proposed = propose_bot(
        BotProposal(bot_id="imp", pipeline_source=hang, tables=["events"]),
        MockSource({"events": []}),
        bots_dir=tmp_path,
        timeout=0.3,
    )
    assert not proposed.valid
    assert any("exceeded" in e for e in proposed.errors)
    assert time.perf_counter() - start < 5


def test_propose_rejects_verdict_records_even_with_note_in_summary(tmp_path):
    # records lack the note even though the summary hand-inserts it -> rejected (structural check)
    bad = (
        "from silmari_runtime.context import BotResult\n"
        "def run(context):\n"
        f"    return BotResult(data=[{{'id': 'x'}}], summary={NOT_A_VERDICT!r})\n"
    )
    proposed = propose_bot(
        BotProposal(bot_id="verdict", pipeline_source=bad, tables=["events"]),
        MockSource({"events": [{"id": 1}]}),
        bots_dir=tmp_path,
    )
    assert not proposed.valid
    assert any("not-a-verdict" in e for e in proposed.errors)


def test_register_tool_returns_error_on_bad_args(tmp_path):
    # malformed tool args (tables not a list) must be reported, never raised into the loop
    toolbox = AuthoringToolbox(MockSource({"events": []}), bots_dir=str(tmp_path))
    out = json.loads(
        toolbox.dispatch(
            "register_bot", {"bot_id": "b", "pipeline_source": "def run(c): ...", "tables": 5}
        )
    )
    assert "error" in out
