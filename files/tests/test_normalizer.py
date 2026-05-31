import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from service.models import CallMetric
from service.normalizer import call_metric_to_row, normalize, session_to_call_metric

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "sample_calls.jsonl"


def _load_all() -> list[dict]:
    rows = []
    with FIXTURES.open() as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


@pytest.fixture
def fixtures() -> list[dict]:
    return _load_all()


def test_normalize_maps_all_fields(fixtures):
    sample = fixtures[0]
    row = normalize(sample)

    assert row["call_id"] == sample["call_id"]
    assert row["tenant_id"] == sample["tenant_id"]
    assert row["duration_seconds"] == sample["duration_seconds"]
    assert row["escalated"] == int(sample["escalated"])
    assert row["variables"]["room_type"] == sample["variables"]["room_type"]
    assert row["started_at"].tzinfo is not None


@pytest.mark.parametrize(
    "idx,label",
    [
        (4, "happy_path"),
        (6, "escalation"),
        (10, "drop"),
        (12, "voicemail"),
        (33, "hi-IN"),
    ],
)
def test_representative_fixtures(idx, label, fixtures):
    raw = fixtures[idx]
    metric = CallMetric.from_api_dict(raw)
    row = call_metric_to_row(metric)

    assert row["call_id"] == raw["call_id"]
    if label == "escalation":
        assert row["escalated"] == 1
    if label == "drop":
        assert row["dropped"] == 1
    if label == "voicemail":
        assert row["pickup_status"] == "voicemail"
    if label == "hi-IN":
        assert row["language"] == "hi-IN"


class _FakeAgent:
    id = 94
    title = "general inquiry about hotel"


class _FakeSession:
    id = 721
    provider_ref_id = "DsXRQBTbBPbghSJfRGAA"
    started_at = datetime(2026, 5, 28, 12, 20, 23, tzinfo=timezone.utc)
    ended_at = None
    created_at = started_at
    duration_seconds = 120
    call_outcome = "answered"
    disposition = "resolved"
    user_turn_count = 7
    collected_variables = {"room_type": "sea-view", "language": "en-IN"}
    end_reason = "End"
    active_agent = _FakeAgent()


def test_session_to_call_metric():
    metric = session_to_call_metric(
        _FakeSession(),
        tenant_id="wks_taj_group",
        default_property_id="thv_goa",
    )
    assert metric.call_id == "DsXRQBTbBPbghSJfRGAA"
    assert metric.resolved is True
    assert metric.variables["room_type"] == "sea-view"
    assert metric.num_turns == 7
    assert metric.num_one_word_replies == 0
