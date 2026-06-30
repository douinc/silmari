# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
import json

import pytest
from silmari_core import DataAccess, MockSource, ScopeViolation
from silmari_runtime.context import Context
from silmari_runtime.ruleset import (
    RulesetError,
    evaluate,
    merge_ruleset,
    run_ruleset,
    validate_ruleset,
)


def _c(field, operator, value, **extra):
    return {"field": field, "operator": operator, "value": value, **extra}


def _rule(rid, *criteria, label="r", combination="and", **kw):
    conditions = {"combination": combination, "criteria": list(criteria)}
    return {"rule_id": rid, "label": label, "conditions": conditions, **kw}


def _doc(*rules, **kw):
    return {"id_field": "host", "source_table": "metrics", "rules": list(rules), **kw}


DOC = _doc(
    _rule(1, _c("cpu", "gt", 90), label="high_cpu", score=0.8, output={"code": "HIGH_CPU"}),
    _rule(
        2,
        _c("thrpt", "relative_decrease", 50, baseline_field="thrpt_base"),
        label="thrpt_drop",
        score=0.7,
        output={"code": "DROP"},
    ),
    _rule(3, _c("status", "text_present", "timeout"), label="timeout", score=0.6),
)

ROWS = [
    {"host": "a", "cpu": 95, "thrpt": 40, "thrpt_base": 100, "status": "ok"},
    {"host": "b", "cpu": 50, "thrpt": 90, "thrpt_base": 100, "status": "timeout"},
]


# --- validation: hard errors ---


def test_validate_ok():
    report = validate_ruleset(DOC)
    assert report.valid and report.rule_count == 3 and report.unsupported == []


def test_unknown_operator_is_hard_error():
    report = validate_ruleset(_doc(_rule(1, _c("x", "bogus", 1))))
    assert not report.valid and report.errors


def test_numeric_operator_requires_number():
    report = validate_ruleset(_doc(_rule(1, _c("x", "lt", "NaN"))))
    assert not report.valid
    assert any("numeric" in e["msg"] for e in report.errors)


def test_relative_decrease_requires_baseline_field():
    report = validate_ruleset(_doc(_rule(1, _c("x", "relative_decrease", 50))))
    assert not report.valid
    assert any("baseline_field" in e["msg"] for e in report.errors)


def test_duplicate_rule_id_is_error():
    report = validate_ruleset(_doc(_rule(1, _c("x", "gt", 1)), _rule(1, _c("y", "gt", 1))))
    assert not report.valid
    assert any("duplicate" in e["msg"] for e in report.errors)


# --- validation: warnings (reported, not fatal) ---


def test_empty_criteria_is_unsupported_warning():
    report = validate_ruleset(_doc(_rule(1)))
    assert report.valid
    assert report.unsupported and "no criteria" in report.unsupported[0].reason


def test_unknown_field_reported_not_silently_skipped():
    report = validate_ruleset(_doc(_rule(1, _c("missing", "gt", 1))), known_fields={"cpu", "host"})
    assert report.valid
    assert report.unsupported and "missing" in report.unsupported[0].reason


def test_text_present_requires_nonempty_string():
    # value omitted -> None; without this guard it would match the substring "none"
    report = validate_ruleset(_doc(_rule(1, {"field": "status", "operator": "text_present"})))
    assert not report.valid
    assert any("text_present" in e["msg"] for e in report.errors)


def test_bool_value_not_accepted_as_numeric():
    report = validate_ruleset(_doc(_rule(1, _c("cpu", "gt", True))))
    assert not report.valid
    assert any("numeric" in e["msg"] for e in report.errors)


# --- evaluation ---


def test_evaluate_fires_expected_rules():
    doc = validate_ruleset(DOC).doc
    assert doc is not None
    signals = evaluate(doc, ROWS)
    fired = {(s.target_id, s.label) for s in signals}
    assert ("a", "high_cpu") in fired
    assert ("a", "thrpt_drop") in fired
    assert ("b", "timeout") in fired
    assert ("b", "high_cpu") not in fired

    high = next(s for s in signals if s.label == "high_cpu")
    assert high.note  # not-a-verdict attached
    assert high.features["rule_id"] == 1
    assert high.features["code"] == "HIGH_CPU"


def test_or_combination():
    rule = _rule(
        1,
        _c("cpu", "gt", 90),
        _c("status", "text_present", "timeout"),
        label="either",
        combination="or",
    )
    doc = validate_ruleset(_doc(rule)).doc
    assert doc is not None
    assert {s.target_id for s in evaluate(doc, ROWS)} == {"a", "b"}


# --- run_ruleset (hot-reload, e2e) ---


def _context(rows):
    scoped = MockSource({"metrics": rows}).scoped(DataAccess(tables=["metrics"]), run_id="r")
    return Context(source=scoped, config={}, run_id="r", as_of="2024-01-01")


def test_run_ruleset_end_to_end(tmp_path):
    path = tmp_path / "ruleset.json"
    path.write_text(json.dumps(DOC))
    res = run_ruleset(_context(ROWS), path)
    assert res.metadata["rules_total"] == 3
    assert len(res.data) == 3
    assert all(d["note"] for d in res.data)


def test_run_ruleset_hot_reload(tmp_path):
    path = tmp_path / "ruleset.json"
    path.write_text(json.dumps(_doc(_rule(1, _c("cpu", "gt", 90), label="high"))))
    assert len(run_ruleset(_context(ROWS), path).data) == 1  # only host a

    path.write_text(json.dumps(_doc(_rule(1, _c("cpu", "gt", 10), label="any"))))
    assert len(run_ruleset(_context(ROWS), path).data) == 2  # edited threshold -> both hosts


def test_run_ruleset_invalid_raises(tmp_path):
    path = tmp_path / "ruleset.json"
    path.write_text(json.dumps(_doc(_rule(1, _c("x", "bogus", 1)))))
    with pytest.raises(RulesetError):
        run_ruleset(_context(ROWS), path)


def test_unsupported_rule_reported_in_metadata(tmp_path):
    path = tmp_path / "ruleset.json"
    path.write_text(json.dumps(_doc(_rule(1, _c("nope", "gt", 1), label="ghost"))))
    res = run_ruleset(_context(ROWS), path)
    assert res.data == []  # never silently emitted
    assert res.metadata["rules_unsupported"][0]["rule_id"] == 1  # explicitly reported


def test_merge_ruleset():
    base = {"$schema_description": "old", "rules": [{"rule_id": 9}], "runtime_state": "keep"}
    proposed = {"$schema_description": "new", "rules": [{"rule_id": 1}]}
    merged = merge_ruleset(base, proposed)
    assert merged["$schema_description"] == "new"
    assert merged["rules"] == [{"rule_id": 1}]
    assert merged["runtime_state"] == "keep"  # non-editable base key preserved


# --- a ruleset is data, bounded by the bot's scope + read-only source ---


def test_ruleset_cannot_read_outside_scope(tmp_path):
    path = tmp_path / "ruleset.json"
    path.write_text(json.dumps(_doc(_rule(1, _c("cpu", "gt", 90)), source_table="secret")))
    with pytest.raises(ScopeViolation):  # source scoped to ["metrics"]
        run_ruleset(_context(ROWS), path)


def test_ruleset_source_injection_blocked(tmp_path):
    path = tmp_path / "ruleset.json"
    doc = _doc(_rule(1, _c("cpu", "gt", 90)), source_table="metrics; DROP TABLE metrics")
    path.write_text(json.dumps(doc))
    with pytest.raises(PermissionError):  # multi-statement / non-SELECT rejected by the guard
        run_ruleset(_context(ROWS), path)


# --- invariant: a rule reported unsupported is never also emitted ---


def test_or_rule_with_one_present_criterion_fires_and_not_reported():
    rule = _rule(1, _c("cpu", "gt", 90), _c("absent", "gt", 1), label="or_one", combination="or")
    report = validate_ruleset(_doc(rule), known_fields={"host", "cpu"})
    assert report.unsupported == []  # can still fire via the present criterion
    fired = {s.target_id for s in evaluate(report.doc, ROWS, known_fields={"host", "cpu"})}
    assert fired == {"a"}


def test_and_rule_with_missing_field_reported_and_not_emitted():
    rule = _rule(1, _c("cpu", "gt", 0), _c("absent", "gt", 1), label="and_miss")
    report = validate_ruleset(_doc(rule), known_fields={"host", "cpu"})
    assert report.unsupported and "absent" in report.unsupported[0].reason
    assert evaluate(report.doc, ROWS, known_fields={"host", "cpu"}) == []  # reported => not emitted


def test_reported_unsupported_never_emits(tmp_path):
    path = tmp_path / "ruleset.json"
    path.write_text(
        json.dumps(
            _doc(
                _rule(1, _c("cpu", "gt", 90), label="ok"),
                _rule(2, _c("ghost", "gt", 1), label="bad"),
            )
        )
    )
    res = run_ruleset(_context(ROWS), path)
    reported = {u["rule_id"] for u in res.metadata["rules_unsupported"]}
    emitted = {d["features"]["rule_id"] for d in res.data}
    assert reported == {2}
    assert reported.isdisjoint(emitted)  # the central invariant


def test_id_field_mismatch_reported_and_not_emitted(tmp_path):
    path = tmp_path / "ruleset.json"
    path.write_text(json.dumps(_doc(_rule(1, _c("cpu", "gt", 90), label="x"), id_field="WRONGID")))
    res = run_ruleset(_context(ROWS), path)
    assert res.data == []  # no identity-less signals emitted
    assert any("id field" in u["reason"] for u in res.metadata["rules_unsupported"])
