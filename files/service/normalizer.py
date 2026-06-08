"""
Pure mapping: zenlabs session / CallMetric → ClickHouse row dict.
No I/O — safe to unit test.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from service.models import CallMetric

_ESCALATION_DISPOSITIONS = frozenset(
    {
        "agent_escalation_immediate",
        "agent_escalation_mid_call",
        "fatal_error_escalated",
    }
)
_HANGUP_DISPOSITIONS = frozenset({"hangup_immediate", "hangup_mid_call"})

_CALL_OUTCOME_PICKUP = {
    "answered": "answered",
    "no_answer": "no_pickup",
    "voicemail": "voicemail",
}

_DISPOSITION_ESCALATION_REASON = {
    "agent_escalation_immediate": "user_request",
    "agent_escalation_mid_call": "agent_unable",
    "fatal_error_escalated": "agent_unable",
    "transfer_unsupported": "user_request",
    "error": "timeout",
}


def _enum_value(value: Any) -> str:
    if value is None:
        return ""
    return str(getattr(value, "value", value))


def _stringify_variables(raw: Any) -> dict[str, str]:
    if not raw or not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


def session_to_call_metric(
    session: Any,
    *,
    tenant_id: str,
    default_property_id: str,
) -> CallMetric:
    """
    Map a zenlabs dashboard InteractionSession to CallMetric.

    Fields not exposed by the API are defaulted (0 / '') per §10.5 — not inferred
    from transcripts.
    """
    session_id = getattr(session, "id", None)
    provider_ref = _enum_value(getattr(session, "provider_ref_id", None))
    call_id = provider_ref or (f"session_{session_id}" if session_id else "unknown")

    agent = getattr(session, "active_agent", None)
    agent_id = str(getattr(agent, "id", "") or "")

    collected = _stringify_variables(getattr(session, "collected_variables", None))
    property_id = collected.get("property_id") or default_property_id

    disposition = _enum_value(getattr(session, "disposition", None))
    call_outcome = _enum_value(getattr(session, "call_outcome", None))

    escalated = disposition in _ESCALATION_DISPOSITIONS
    escalation_reason = _DISPOSITION_ESCALATION_REASON.get(disposition, "") if escalated else ""

    dropped = disposition in _HANGUP_DISPOSITIONS
    resolved = disposition == "resolved"

    pickup_status = _CALL_OUTCOME_PICKUP.get(call_outcome, "answered")
    if call_outcome in ("", "unknown") and getattr(session, "duration_seconds", 0) in (0, None):
        pickup_status = "no_pickup"

    user_turns = getattr(session, "user_turn_count", None) or 0
    # API reports user turns only; agent turns not exposed — store user count as floor.
    num_turns = int(user_turns) if user_turns else 0

    language = collected.get("language") or collected.get("caller_language") or "en-IN"
    end_node = _enum_value(getattr(session, "end_reason", None)) or disposition

    started_at: Optional[datetime] = getattr(session, "started_at", None) or getattr(
        session, "created_at", None
    )
    if started_at is None:
        started_at = datetime.now(timezone.utc)

    ended_at: Optional[datetime] = getattr(session, "ended_at", None)
    duration_seconds = int(getattr(session, "duration_seconds", None) or 0)

    return CallMetric(
        call_id=call_id,
        tenant_id=tenant_id,
        agent_id=agent_id,
        property_id=property_id,
        started_at=started_at,
        ended_at=ended_at,

        duration_seconds=duration_seconds,
        num_turns=num_turns,
        num_one_word_replies=0,
        escalated=escalated,
        escalation_reason=escalation_reason,
        dropped=dropped,
        language=language,
        pickup_status=pickup_status,
        resolved=resolved,
        end_node=end_node,
        variables=collected,
    )


def call_metric_to_row(call: CallMetric) -> dict[str, Any]:
    """CallMetric → dict for clickhouse-connect insert (no ingested_at)."""

    def to_utc(dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    return {
        "call_id": call.call_id,
        "tenant_id": call.tenant_id,
        "agent_id": call.agent_id,
        "property_id": call.property_id or "",
        "started_at": to_utc(call.started_at),
        "ended_at": to_utc(call.ended_at),
        "duration_seconds": call.duration_seconds,
        "num_turns": call.num_turns,
        "num_one_word_replies": call.num_one_word_replies,
        "escalated": int(call.escalated),
        "escalation_reason": call.escalation_reason or "",
        "dropped": int(call.dropped),
        "language": call.language or "en-IN",
        "pickup_status": call.pickup_status or "answered",
        "resolved": int(call.resolved),
        "end_node": call.end_node or "",
        "variables": call.variables,
    }


def normalize(call: CallMetric | dict[str, Any]) -> dict[str, Any]:
    """Accept CallMetric or dict (fixtures); return CH insert row."""
    if isinstance(call, dict):
        metric = CallMetric.from_api_dict(call)
    else:
        metric = call
    return call_metric_to_row(metric)
