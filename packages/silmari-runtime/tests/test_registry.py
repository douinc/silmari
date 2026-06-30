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
