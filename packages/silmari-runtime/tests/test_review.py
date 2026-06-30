# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from silmari_runtime.context import BotResult
from silmari_runtime.review import ReviewStore, build_cases, tuning_report
from silmari_runtime.store import ResultStore


def test_set_get_decision():
    rv = ReviewStore()
    rv.set_decision("bot", "r1", "0", "accepted", note="ok", reviewer="alice")
    decision = rv.get("bot", "r1", "0")
    assert decision is not None
    assert decision.decision == "accepted"
    assert decision.note == "ok"
    assert decision.reviewer == "alice"
    assert rv.get("bot", "r1", "99") is None  # pending == no row


def test_invalid_decision_rejected():
    with pytest.raises(ValueError):
        ReviewStore().set_decision("b", "r", "0", "bogus")


def test_decision_is_upserted():
    rv = ReviewStore()
    rv.set_decision("bot", "r1", "0", "accepted")
    rv.set_decision("bot", "r1", "0", "rejected", reviewer="bob")  # overwrite
    decision = rv.get("bot", "r1", "0")
    assert decision is not None
    assert decision.decision == "rejected"
    assert decision.reviewer == "bob"


def test_decisions_for_run_and_tally():
    rv = ReviewStore()
    rv.set_decision("bot", "r1", "0", "accepted")
    rv.set_decision("bot", "r1", "1", "rejected")
    assert set(rv.decisions_for_run("bot", "r1")) == {"0", "1"}
    tally = rv.tally("bot", "r1", total_cases=3)
    assert tally == {"accepted": 1, "rejected": 1, "reviewed": 2, "total": 3, "pending": 1}


def test_build_cases():
    cases = build_cases([{"score": 0.9, "target_id": "a"}, {"target_id": "b"}])
    assert cases[0] == ("0", 0.9, {"score": 0.9, "target_id": "a"})
    assert cases[1][1] is None  # no score


def test_tuning_recommends_f1_best_threshold():
    store = ResultStore()
    store.create_running("bot", "r1", "")
    store.mark_completed(
        "r1",
        BotResult(
            data=[
                {"target_id": "a", "score": 0.9},
                {"target_id": "b", "score": 0.8},
                {"target_id": "c", "score": 0.3},
            ]
        ),
    )
    reviews = ReviewStore()
    reviews.set_decision("bot", "r1", "0", "accepted")
    reviews.set_decision("bot", "r1", "1", "accepted")
    reviews.set_decision("bot", "r1", "2", "rejected")

    report = tuning_report(store, reviews, "bot")
    assert report.labeled == 3
    assert report.accepted == 2
    assert report.rejected == 1
    assert report.recommended is not None
    # threshold 0.8 flags a+b (both accepted) -> precision 1.0, recall 1.0, F1 1.0
    assert report.recommended.threshold == 0.8
    assert report.recommended.f1 == 1.0
