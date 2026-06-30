from silmari_core import DataAccess, MockSource
from silmari_runtime.context import BotResult, Context


def test_context_holds_scoped_source() -> None:
    src = MockSource({"demo.orders": [{"id": 1}]})
    scoped = src.scoped(DataAccess(tables=["demo.orders"]), run_id="r1")
    ctx = Context(source=scoped, config={"k": "v"}, run_id="r1", as_of="2024-01-01")
    assert ctx.run_id == "r1"
    assert ctx.config["k"] == "v"
    assert ctx.source.query("SELECT * FROM demo.orders") == [{"id": 1}]


def test_bot_result_defaults() -> None:
    r = BotResult(data=[{"a": 1}])
    assert r.metadata == {}
    assert r.summary == ""
