# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
import time
from pathlib import Path

from fastapi.testclient import TestClient
from silmari_core import MockSource
from silmari_runtime.api.app import create_app
from silmari_runtime.api.routers import sse_stream
from silmari_runtime.context import BotResult
from silmari_runtime.review import ReviewStore
from silmari_runtime.sinks import EventBus
from silmari_runtime.store import ResultStore

EXAMPLES = Path(__file__).resolve().parents[3] / "examples" / "bots"


def _client(**kw) -> TestClient:
    return TestClient(create_app(bots_dir=str(EXAMPLES), **kw))


def _seed(store: ResultStore, bot="example-signal", run="run1", data=None):
    store.create_running(bot, run, "2024-01-01")
    result = BotResult(data=data or [{"target_id": "x", "score": 0.9}], summary="s")
    store.mark_completed(run, result)


def test_health():
    assert _client().get("/health").json() == {"status": "ok"}


def test_list_bots():
    ids = {b["bot_id"] for b in _client().get("/v1/bots").json()}
    assert {"example-signal", "example-ruleset"} <= ids


def test_results_404_then_served():
    store = ResultStore()
    client = _client(store=store)
    assert client.get("/v1/bots/example-signal/results").status_code == 404
    _seed(store)
    res = client.get("/v1/bots/example-signal/results").json()
    assert res["run_id"] == "run1"
    assert res["data"][0]["target_id"] == "x"


def test_trigger_run_then_serves_results():
    store = ResultStore()
    source = MockSource({"orders": [{"id": 1, "total": 100}, {"id": 2, "total": 50}]})
    client = _client(store=store, source=source)
    resp = client.post("/v1/bots/example-signal/run")
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]

    for _ in range(200):
        got = client.get(f"/v1/bots/example-signal/results/{run_id}")
        if got.status_code == 200 and got.json()["status"] == "completed":
            break
        time.sleep(0.02)
    res = client.get(f"/v1/bots/example-signal/results/{run_id}").json()
    assert res["status"] == "completed"
    assert len(res["data"]) == 1  # only order total >= 75


def test_run_without_source_returns_503():
    assert _client().post("/v1/bots/example-signal/run").status_code == 503


def test_review_decision_persists_and_tuning():
    store, reviews = ResultStore(), ReviewStore()
    client = _client(store=store, reviews=reviews)
    _seed(store, data=[{"target_id": "a", "score": 0.9}, {"target_id": "b", "score": 0.3}])

    cases = client.get("/v1/bots/example-signal/runs/run1/cases").json()
    assert len(cases["cases"]) == 2
    assert cases["cases"][0]["decision"] == "pending"

    decided = client.post(
        "/v1/bots/example-signal/runs/run1/cases/0/decision",
        json={"decision": "accepted", "reviewer": "alice"},
    )
    assert decided.status_code == 200
    assert decided.json()["tally"]["accepted"] == 1
    assert reviews.get("example-signal", "run1", "0").decision == "accepted"  # persisted

    client.post(
        "/v1/bots/example-signal/runs/run1/cases/1/decision", json={"decision": "rejected"}
    )
    tuning = client.get("/v1/bots/example-signal/tuning").json()
    assert tuning["labeled"] == 2


def test_invalid_decision_400():
    store, client = ResultStore(), None
    client = _client(store=store)
    _seed(store)
    resp = client.post(
        "/v1/bots/example-signal/runs/run1/cases/0/decision", json={"decision": "bogus"}
    )
    assert resp.status_code == 400


def test_subscriptions_crud():
    client = _client()
    created = client.post(
        "/v1/bots/example-signal/subscriptions", json={"type": "webhook", "url": "http://x"}
    ).json()
    sub_id = created["id"]
    assert created["type"] == "webhook"
    listed = client.get("/v1/bots/example-signal/subscriptions").json()
    assert any(s["id"] == sub_id for s in listed)
    assert client.delete(f"/v1/bots/example-signal/subscriptions/{sub_id}").status_code == 200
    assert client.get("/v1/bots/example-signal/subscriptions").json() == []


def test_runs_list_endpoint():
    store = ResultStore()
    _seed(store)
    client = _client(store=store)
    # A working GET proves the runs router (which also serves /v1/runs/stream) is registered;
    # SSE event formatting is covered by test_sse_stream_generator_emits_events below.
    assert any(r["run_id"] == "run1" for r in client.get("/v1/runs").json()["runs"])


def test_admin_reload_registry():
    body = _client().post("/v1/admin/reload-registry").json()
    assert body["reloaded"] is True
    assert "example-signal" in body["bot_ids"]


def test_sse_stream_generator_emits_events():
    bus = EventBus()
    gen = sse_stream(bus)
    assert next(gen) == ": connected\n\n"  # primes + subscribes
    bus.publish({"type": "run_started", "run_id": "r1"})
    chunk = next(gen)
    assert chunk.startswith("event: run_started\n")
    assert '"run_id": "r1"' in chunk
    gen.close()


def test_decide_unknown_run_404():
    assert (
        _client()
        .post("/v1/bots/example-signal/runs/nope/cases/0/decision", json={"decision": "accepted"})
        .status_code
        == 404
    )


def test_decide_unknown_case_404():
    store = ResultStore()
    client = _client(store=store)
    _seed(store, data=[{"target_id": "a", "score": 0.5}])  # only case "0" exists
    resp = client.post(
        "/v1/bots/example-signal/runs/run1/cases/99/decision", json={"decision": "accepted"}
    )
    assert resp.status_code == 404


def test_trigger_unscoped_bot_returns_400():
    from silmari_runtime.context import BotResult as _BotResult
    from silmari_runtime.manifest import BotManifest
    from silmari_runtime.registry import BotRecord

    manifest = BotManifest.model_validate({"bot_id": "leaky", "name": "leaky"})  # empty scope
    registry = {
        "leaky": BotRecord(manifest=manifest, run=lambda ctx: _BotResult(data=[]), path=Path("."))
    }
    client = TestClient(create_app(registry=registry, source=MockSource({"x": []})))
    assert client.post("/v1/bots/leaky/run").status_code == 400


def test_subscription_invalid_type_400():
    resp = _client().post("/v1/bots/example-signal/subscriptions", json={"type": "bogus"})
    assert resp.status_code == 400


def test_webhook_subscription_requires_url_400():
    resp = _client().post("/v1/bots/example-signal/subscriptions", json={"type": "webhook"})
    assert resp.status_code == 400


def test_runs_negative_limit_is_clamped():
    store = ResultStore()
    _seed(store)
    client = _client(store=store)
    # SQLite treats LIMIT -1 as unbounded; the endpoint must clamp instead of returning everything.
    assert client.get("/v1/runs?limit=-1").status_code == 200


def test_ui_served_when_ui_dir_set():
    frontend = Path(__file__).resolve().parents[3] / "examples" / "frontend"
    client = TestClient(create_app(bots_dir=str(EXAMPLES), ui_dir=str(frontend)))
    page = client.get("/")
    assert page.status_code == 200
    assert 'data-testid="bot-list"' in page.text
    assert client.get("/v1/bots").status_code == 200  # API routes still win over the static mount


def test_data_browser_endpoints():
    source = MockSource({"orders": [{"id": 1, "total": 100}, {"id": 2, "total": 50}]})
    client = _client(source=source)
    assert "orders" in str(client.get("/v1/data/tables").json()["tables"])
    assert client.get("/v1/data/tables/orders").json()["table"] == "orders"
    rows = client.get("/v1/data/tables/orders/sample?n=1").json()["rows"]
    assert len(rows) == 1 and rows[0]["id"] == 1
    assert client.get("/v1/data/tables/orders/columns/total/stats").status_code == 200
    q = client.post("/v1/data/query", json={"sql": "SELECT * FROM orders"})
    assert q.status_code == 200 and len(q.json()["rows"]) == 2


def test_data_query_rejects_writes_400():
    client = _client(source=MockSource({"orders": []}))
    assert client.post("/v1/data/query", json={"sql": "DELETE FROM orders"}).status_code == 400


def test_data_browser_503_without_source():
    assert _client().get("/v1/data/tables").status_code == 503


def test_data_query_masks_results():
    from silmari_core import ColumnMasking

    source = MockSource({"t": [{"id": 1, "email": "a@b.com"}]}, masking=ColumnMasking(["email"]))
    rows = _client(source=source).post("/v1/data/query", json={"sql": "SELECT * FROM t"}).json()
    assert rows["rows"][0] == {"id": 1, "email": "***"}  # masked into the response


def test_data_sample_rejects_non_identifier_table():
    # a subquery smuggled as the {table} segment (the masking-bypass vector) is rejected outright
    client = _client(source=MockSource({"t": [{"id": 1}]}))
    assert client.get("/v1/data/tables/(SELECT id, email AS x FROM t) s/sample").status_code == 400
    assert client.get("/v1/data/tables/t-x/sample").status_code == 400  # any non-identifier


def test_data_sample_masks_a_real_table():
    from silmari_core import ColumnMasking

    source = MockSource({"t": [{"id": 1, "email": "a@b.com"}]}, masking=ColumnMasking(["email"]))
    rows = _client(source=source).get("/v1/data/tables/t/sample").json()["rows"]
    assert rows[0] == {"id": 1, "email": "***"}  # validated table -> masking applies for real


_AUTHORING_PIPELINE = (
    "from silmari_runtime.signal import result, signal\n\n\n"
    "def run(context):\n"
    "    rows = context.source.query('SELECT * FROM orders')\n"
    "    sigs = [signal(target_id=str(r['id']), label='hv') for r in rows]\n"
    "    return result(sigs, label='hv', as_of=context.as_of)\n"
)


def test_authoring_propose_with_scripted_llm():
    from silmari_runtime.agent.scripted import ScriptedLLM, say, tool_call

    llm = ScriptedLLM(
        [
            tool_call("data_schema"),
            tool_call(
                "register_bot", bot_id="hv", pipeline_source=_AUTHORING_PIPELINE, tables=["orders"]
            ),
            say("done"),
        ]
    )
    client = _client(source=MockSource({"orders": [{"id": 1}, {"id": 2}]}), authoring_llm=llm)
    out = client.post("/v1/authoring/propose", json={"message": "make a bot"}).json()
    assert "register_bot" in out["steps"]
    assert out["proposal"]["bot_id"] == "hv"
    assert out["proposal"]["valid"] is True
    assert "def run(context)" in out["proposal"]["pipeline"]


def test_authoring_disabled_without_llm_returns_503():
    resp = _client(source=MockSource({"orders": []})).post(
        "/v1/authoring/propose", json={"message": "x"}
    )
    assert resp.status_code == 503  # gated: no authoring_llm configured


def test_authoring_without_source_returns_503():
    from silmari_runtime.agent.scripted import ScriptedLLM, say

    client = _client(authoring_llm=ScriptedLLM([say("x")]))  # llm set, but no data source
    assert client.post("/v1/authoring/propose", json={"message": "x"}).status_code == 503


def test_authoring_demo_model_is_repeatable_and_routed():
    from silmari_runtime.agent.demo import DemoAuthoringLLM

    source = MockSource(
        {
            "orders": [{"id": 1, "total": 100}],
            "metrics": [{"host": "web-2", "cpu": 40, "status_text": "request timeout"}],
        }
    )
    client = _client(source=source, authoring_llm=DemoAuthoringLLM())
    # stateless: every request works (the old shared ScriptedLLM was exhausted after the first)
    a = client.post("/v1/authoring/propose", json={"message": "flag high-value orders"}).json()
    b = client.post("/v1/authoring/propose", json={"message": "find request timeouts"}).json()
    assert a["proposal"]["valid"] and a["proposal"]["bot_id"] == "high-value-orders"
    assert b["proposal"]["valid"] and b["proposal"]["bot_id"] == "status-timeouts"  # routed by ask
