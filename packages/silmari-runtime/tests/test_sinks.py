import queue

import silmari_runtime.sinks as sinks_mod
from silmari_runtime.sinks import EventBus, Subscription, SubscriptionStore, deliver_webhooks


def test_event_bus_pub_sub():
    bus = EventBus()
    q = bus.subscribe()
    bus.publish({"type": "run_started", "run_id": "r1"})
    assert q.get_nowait() == {"type": "run_started", "run_id": "r1"}
    bus.unsubscribe(q)
    bus.publish({"type": "run_completed"})  # no subscribers -> no error
    assert q.empty()


def test_event_bus_drops_when_full_without_blocking():
    bus = EventBus(maxsize=2)
    bus.subscribe()  # never drained
    for i in range(10):
        bus.publish({"type": "e", "i": i})  # must not raise / block


def test_subscription_store_register_list_remove():
    store = SubscriptionStore()
    store.register(Subscription(id="s1", bot_id="bot", type="webhook", url="http://x"))
    assert [s.id for s in store.list("bot")] == ["s1"]
    assert store.remove("bot", "s1") is True
    assert store.list("bot") == []
    assert store.remove("bot", "missing") is False


def test_deliver_webhooks_posts_and_swallows_errors(monkeypatch):
    posted = []
    monkeypatch.setattr(sinks_mod.httpx, "post", lambda url, **kw: posted.append((url, kw["json"])))
    subs = [
        Subscription(id="s1", bot_id="b", type="webhook", url="http://hook"),
        Subscription(id="s2", bot_id="b", type="sse"),  # not a webhook -> skipped
    ]
    deliver_webhooks({"run_id": "r1"}, subs)
    assert posted == [("http://hook", {"run_id": "r1"})]


def test_deliver_webhooks_env_expansion(monkeypatch):
    monkeypatch.setenv("HOOK_TOKEN", "secret123")
    captured = []
    monkeypatch.setattr(sinks_mod.httpx, "post", lambda url, **kw: captured.append(url))
    deliver_webhooks(
        {"x": 1}, [Subscription(id="s", bot_id="b", type="webhook", url="http://h/${HOOK_TOKEN}")]
    )
    assert captured == ["http://h/secret123"]


def test_unsubscribe_is_idempotent():
    bus = EventBus()
    q: queue.Queue = bus.subscribe()
    bus.unsubscribe(q)
    bus.unsubscribe(q)  # no error
