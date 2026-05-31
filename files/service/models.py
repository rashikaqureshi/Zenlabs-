from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class CallMetric(BaseModel):
    """Per-call metric contract (§6). Zenlabs is source of truth."""

    call_id: str
    tenant_id: str
    agent_id: str = ""
    property_id: str = ""
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_seconds: int = 0
    num_turns: int = 0
    num_one_word_replies: int = 0
    escalated: bool = False
    escalation_reason: str = ""
    dropped: bool = False
    language: str = "en-IN"
    pickup_status: str = "answered"
    resolved: bool = False
    end_node: str = ""
    variables: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def from_api_dict(cls, data: dict[str, Any]) -> "CallMetric":
        """Parse fixture JSON or API-shaped dict."""
        payload = dict(data)
        variables = payload.get("variables") or {}
        payload["variables"] = {str(k): str(v) for k, v in variables.items()}
        return cls.model_validate(payload)
