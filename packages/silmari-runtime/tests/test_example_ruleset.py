# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

from silmari_core import MockSource
from silmari_runtime.executor import run_bot
from silmari_runtime.registry import load_registry
from silmari_runtime.store import STATUS_COMPLETED, ResultStore

EXAMPLES = Path(__file__).resolve().parents[3] / "examples" / "bots"

METRICS = [
    {"host": "web-1", "cpu": 95, "throughput": 40, "throughput_baseline": 100, "status_text": "ok"},
    {
        "host": "web-2",
        "cpu": 40,
        "throughput": 95,
        "throughput_baseline": 100,
        "status_text": "request timeout",
    },
]


def test_example_ruleset_runs_end_to_end():
    record = load_registry(EXAMPLES)["example-ruleset"]
    run = run_bot(record, MockSource({"metrics": METRICS}), ResultStore(), trigger="manual")
    assert run.status == STATUS_COMPLETED
    labels = {d["label"] for d in run.data}
    assert {"high_cpu", "throughput_drop", "status_timeout"} <= labels
    assert all(d["note"] for d in run.data)  # every signal carries the not-a-verdict note
