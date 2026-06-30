# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
from silmari_runtime.signal import NOT_A_VERDICT, confidence_band, result, signal


def test_confidence_band() -> None:
    assert confidence_band(0.9) == "high"
    assert confidence_band(0.65) == "medium-high"
    assert confidence_band(0.4) == "medium"
    assert confidence_band(0.1) == "low"


def test_signal_attaches_note_and_band() -> None:
    s = signal("e1", "readmission", score=0.85, evidence=["x"], subject={"dept": "cardio"})
    assert s.note == NOT_A_VERDICT
    assert s.confidence == "high"
    assert s.score == 0.85
    rec = s.as_record()
    assert rec["target_id"] == "e1"
    assert rec["subject"] == {"dept": "cardio"}
    assert rec["note"] == NOT_A_VERDICT


def test_signal_clamps_score() -> None:
    assert signal("e", "l", score=1.5).score == 1.0
    assert signal("e", "l", score=-0.2).score == 0.0


def test_signal_without_score() -> None:
    s = signal("e", "l")
    assert s.score is None
    assert s.confidence == ""


def test_result_filters_sorts_and_frames() -> None:
    sigs = [
        signal("a", "l", score=0.9),
        signal("b", "l", score=0.3),
        signal("c", "l", score=0.6),
    ]
    r = result(sigs, label="l", threshold=0.5, as_of="2024-01-01")
    assert r.metadata["cohort_size"] == 3
    assert r.metadata["flagged"] == 2
    assert r.metadata["kind"] == "signal"
    assert [d["target_id"] for d in r.data] == ["a", "c"]  # filtered >=0.5, sorted desc
    assert all(d["note"] == NOT_A_VERDICT for d in r.data)
    assert NOT_A_VERDICT in r.summary
