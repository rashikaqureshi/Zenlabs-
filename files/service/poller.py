from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from service.config import settings
from service.models import CallMetric
from service.normalizer import session_to_call_metric
from service.zenlabs_client import get_client


def _session_started_at(session: Any) -> datetime | None:
    started = getattr(session, "started_at", None) or getattr(session, "created_at", None)
    if started is None:
        return None
    if started.tzinfo is None:
        return started.replace(tzinfo=timezone.utc)
    return started.astimezone(timezone.utc)


def fetch_calls_since(cursor: datetime, *, page_size: int = 500) -> list[CallMetric]:
    """
    Page through dashboard sessions and return metrics with started_at > cursor.
    """
    client = get_client()
    metrics: list[CallMetric] = []
    page = 1

    if cursor.tzinfo is None:
        cursor = cursor.replace(tzinfo=timezone.utc)

    while True:
        page_result = client.voice.dashboard_sessions_list(page=page, page_size=page_size)
        batch = page_result.results or []
        if not batch:
            break

        for session in batch:
            started = _session_started_at(session)
            if started is None or started <= cursor:
                continue
            metrics.append(
                session_to_call_metric(
                    session,
                    tenant_id=settings.tenant_id,
                    default_property_id=settings.default_property_id,
                )
            )

        if not page_result.next:
            break
        page += 1

    metrics.sort(key=lambda m: m.started_at)
    return metrics
