import json

import pytest
from silmari_runtime.proposals import ProposalStore
from silmari_runtime.ruleset import RulesetError

VALID = {
    "id_field": "host",
    "source_table": "metrics",
    "rules": [
        {
            "rule_id": 1,
            "label": "r",
            "conditions": {"criteria": [{"field": "cpu", "operator": "gt", "value": 90}]},
        }
    ],
}
INVALID = {
    "rules": [
        {
            "rule_id": 1,
            "conditions": {"criteria": [{"field": "x", "operator": "bogus", "value": 1}]},
        }
    ]
}


def test_stage_get_discard(tmp_path):
    store = ProposalStore(tmp_path)
    store.stage("bot", VALID, reviewer="alice")
    proposal = store.get("bot")
    assert proposal is not None
    assert proposal.reviewer == "alice"
    assert proposal.ruleset == VALID
    assert store.discard("bot") is True
    assert store.get("bot") is None


def test_stage_invalid_rejected(tmp_path):
    with pytest.raises(RulesetError):
        ProposalStore(tmp_path).stage("bot", INVALID)


def test_approve_writes_live_ruleset_and_discards(tmp_path):
    store = ProposalStore(tmp_path / "proposals")
    live = tmp_path / "ruleset.json"
    live.write_text(json.dumps({"rules": [], "runtime_state": "keep"}))

    store.stage("bot", VALID)
    report = store.approve("bot", live)

    assert report.valid
    written = json.loads(live.read_text())
    assert written["rules"] == VALID["rules"]
    assert written["runtime_state"] == "keep"  # non-editable base key preserved
    assert store.get("bot") is None  # discarded after approve


def test_approve_without_proposal_raises(tmp_path):
    with pytest.raises(RulesetError):
        ProposalStore(tmp_path).approve("bot", tmp_path / "ruleset.json")


def test_path_traversal_bot_id_rejected(tmp_path):
    with pytest.raises(RulesetError):
        ProposalStore(tmp_path).stage("../evil", VALID)
