from __future__ import annotations

from typing import Any

from service.clickhouse_client import get_client

_COLUMNS = [
    "call_id",
    "tenant_id",
    "agent_id",
    "property_id",
    "started_at",
    "ended_at",
    "duration_seconds",
    "num_turns",
    "num_one_word_replies",
    "escalated",
    "escalation_reason",
    "dropped",
    "language",
    "pickup_status",
    "resolved",
    "end_node",
    "variables",
]


def insert_calls(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0

    data = [[row[col] for col in _COLUMNS] for row in rows]
    client = get_client()
    client.insert("calls", data, column_names=_COLUMNS)
    return len(rows)
