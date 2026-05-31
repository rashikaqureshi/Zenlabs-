"""Double-ingest → single logical row (ReplacingMergeTree + FINAL)."""

import json
from pathlib import Path

import pytest

from service.clickhouse_client import get_client
from service.normalizer import normalize
from service.writer import insert_calls

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample_calls.jsonl"


@pytest.fixture(scope="module")
def ch_ready():
    try:
        client = get_client()
        client.command("SELECT 1")
    except Exception as exc:
        pytest.skip(f"ClickHouse not available: {exc}")
    ddl_path = Path(__file__).resolve().parent.parent / "sql" / "001_init.sql"
    for statement in ddl_path.read_text().split(";"):
        stmt = statement.strip()
        if stmt:
            client.command(stmt)
    client.command("TRUNCATE TABLE IF EXISTS calls")
    return client


def test_double_ingest_single_row(ch_ready):
    line = next(FIXTURE.open())
    raw = json.loads(line)
    row = normalize(raw)
    call_id = row["call_id"]

    insert_calls([row])
    insert_calls([row])

    ch_ready.command("OPTIMIZE TABLE calls FINAL")

    result = ch_ready.query(
        """
        SELECT count()
        FROM calls FINAL
        WHERE call_id = %(call_id)s
        """,
        parameters={"call_id": call_id},
    )
    assert result.result_rows[0][0] == 1
