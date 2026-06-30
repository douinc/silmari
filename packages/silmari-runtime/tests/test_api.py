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
