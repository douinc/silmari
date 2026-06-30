# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
import importlib.util

from silmari_core import DataAccess, MockSource
from silmari_runtime.context import BotResult, Context
from silmari_runtime.prediction import prediction, prediction_result
from silmari_runtime.scaffold import create_bot
from silmari_runtime.signal import NOT_A_VERDICT


def test_prediction_clamps_bands_and_carries_note():
    high = prediction("e1", 1.5, evidence=["x"])  # over 1 -> clamped
    assert high.score == 1.0
    assert high.confidence == "high"
    assert high.note == NOT_A_VERDICT
    low = prediction("e2", -0.2)  # under 0 -> clamped
    assert low.score == 0.0
    assert low.confidence == "low"


def test_prediction_result_is_tagged_prediction():
    preds = [prediction("a", 0.9), prediction("b", 0.3)]
    res = prediction_result(preds, label="risk", threshold=0.5, as_of="2024-01-01")
    assert res.metadata["kind"] == "prediction"
    assert res.metadata["flagged"] == 1  # only 0.9 >= 0.5
    assert res.data[0]["target_id"] == "a"
    assert all(r["note"] == NOT_A_VERDICT for r in res.data)
    assert "prediction(s)" in res.summary
    assert NOT_A_VERDICT in res.summary


def test_scaffold_prediction_kind_runs(tmp_path):
    bot_dir = create_bot("pred-bot", kind="prediction", bots_dir=tmp_path)
    pipeline = bot_dir / "pipeline.py"
    assert "prediction_result" in pipeline.read_text()

    spec = importlib.util.spec_from_file_location("pred_pipeline", pipeline)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    source = MockSource({"your_table": [{"id": 1}]})
    context = Context(
        source=source.scoped(DataAccess(tables=["your_table"]), run_id="t"),
        config={},
        run_id="t",
        as_of="2024-01-01",
    )
    res = module.run(context)
    assert isinstance(res, BotResult)
    assert res.metadata["kind"] == "prediction"
    assert res.data[0]["note"] == NOT_A_VERDICT
