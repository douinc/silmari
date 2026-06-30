"""Example signal bot: flag orders at/above a total threshold as review-priority signals.

Reads only the ``orders`` table (its declared scope), and emits one Signal per high-value order,
each framed with the not-a-verdict note. A human reviewer decides what to do with the lead.
"""

from __future__ import annotations

from silmari_runtime.context import BotResult, Context
from silmari_runtime.signal import result, signal

_THRESHOLD = 75


def run(context: Context) -> BotResult:
    rows = context.source.query("SELECT id, total FROM orders")
    signals = [
        signal(
            target_id=str(row["id"]),
            label="high_value_order",
            score=min(1.0, row["total"] / 100.0),
            evidence=[f"order total {row['total']}"],
            subject={"order_id": row["id"]},
        )
        for row in rows
        if row["total"] >= _THRESHOLD
    ]
    return result(signals, label="high_value_order", as_of=context.as_of)
