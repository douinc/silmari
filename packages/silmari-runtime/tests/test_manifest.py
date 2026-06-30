import pytest
from pydantic import ValidationError
from silmari_runtime.manifest import BotManifest


def test_minimal_manifest_defaults() -> None:
    m = BotManifest(bot_id="b", name="B")
    assert m.kind == "signal"
    assert m.created_via == "manual"
    assert m.data_access.tables == []
    assert m.trigger.timezone == "UTC"
    assert m.output.format == "json"


def test_manifest_from_dict() -> None:
    m = BotManifest.model_validate(
        {
            "bot_id": "missed-codes",
            "name": "Missed codes",
            "kind": "prediction",
            "trigger": {"type": "schedule", "cron": "0 6 * * *"},
            "data_access": {"tables": ["demo.orders", "demo.customers"], "as_of": "D-1"},
            "sinks": [{"type": "webhook", "url": "http://x"}],
        }
    )
    assert m.kind == "prediction"
    assert m.trigger.cron == "0 6 * * *"
    assert m.data_access.tables == ["demo.orders", "demo.customers"]
    assert m.sinks[0].type == "webhook"


def test_invalid_kind_rejected() -> None:
    with pytest.raises(ValidationError):
        BotManifest(bot_id="b", name="B", kind="bogus")  # type: ignore[arg-type]


def test_invalid_bot_id_rejected() -> None:
    with pytest.raises(ValidationError):
        BotManifest(bot_id="Bad Id", name="x")  # spaces/uppercase not allowed
