"""
Ingest cursor stored in ClickHouse (ingest_cursor table).
Restart-safe: one row per tenant_id, ReplacingMergeTree keeps latest.
"""

from __future__ import annotations

from datetime import datetime, timezone

from service.clickhouse_client import get_client
from service.config import settings

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def load_cursor(tenant_id: str | None = None) -> datetime:
    tenant_id = tenant_id or settings.tenant_id
    client = get_client()
    result = client.query(
        """
        SELECT cursor_value
        FROM ingest_cursor FINAL
        WHERE tenant_id = %(tenant_id)s
        LIMIT 1
        """,
        parameters={"tenant_id": tenant_id},
    )
    if not result.result_rows:
        return _EPOCH
    value = result.result_rows[0][0]
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return _EPOCH


def save_cursor(tenant_id: str, cursor_value: datetime) -> None:
    if cursor_value.tzinfo is None:
        cursor_value = cursor_value.replace(tzinfo=timezone.utc)
    else:
        cursor_value = cursor_value.astimezone(timezone.utc)

    client = get_client()
    client.insert(
        "ingest_cursor",
        [[tenant_id, cursor_value]],
        column_names=["tenant_id", "cursor_value"],
    )
