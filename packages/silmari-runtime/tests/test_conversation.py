from silmari_runtime.agent.conversation import ConversationStore


def test_append_and_messages_exclude_system():
    store = ConversationStore()
    store.append("c1", {"role": "user", "content": "hi"})
    store.append("c1", {"role": "system", "content": "sys"})  # excluded from messages()
    store.append("c1", {"role": "assistant", "content": "hello"})
    msgs = store.messages("c1")
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert [m["content"] for m in msgs] == ["hi", "hello"]


def test_conversations_lists_distinct_ids():
    store = ConversationStore()
    store.append("a", {"role": "user", "content": "x"})
    store.append("b", {"role": "user", "content": "y"})
    ids = {c["conversation_id"] for c in store.conversations()}
    assert ids == {"a", "b"}


def test_messages_ordered_by_seq():
    store = ConversationStore()
    for i in range(5):
        store.append("c", {"role": "user", "content": str(i)})
    assert [m["content"] for m in store.messages("c")] == ["0", "1", "2", "3", "4"]
