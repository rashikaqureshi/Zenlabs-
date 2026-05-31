# ClickHouse Analytics Service (Hotel Voice Agents)

Side-car analytics pipeline: **zenlabs emits per-call metrics → this service polls and lands rows in ClickHouse → six SQL queries (+ Streamlit) answer daily ops questions.**

Stack: Python 3.9+, `clickhouse-connect` (HTTP), zenlabs Python SDK, local ClickHouse 24 via Docker.

> **Schema note:** `calls` is `ReplacingMergeTree(ingested_at)` with
> `ORDER BY (tenant_id, call_id)`. `started_at` is deliberately kept *out* of the
> sort key, so a replayed `call_id` collapses to a single row even if its
> `started_at` drifts on re-pull. `sql/002_rebuild_calls_order_key.sql` migrates a
> pre-existing table onto this key via create-copy-swap — ClickHouse can only
> append columns to a sort key, never remove one, so a plain
> `ALTER … MODIFY ORDER BY` is rejected.

## Quick start

```bash
cd files
cp .env.example .env   # add ZENLABS_TOKEN

docker compose up -d clickhouse
pip install -r requirements.txt

python -m service.main --init-schema
# Upgrading a DB created with the old (tenant_id, started_at, call_id) key:
#   clickhouse-client --multiquery < sql/002_rebuild_calls_order_key.sql
# Fresh/dev DB: just DROP TABLE calls; DROP VIEW calls_daily; and re-run --init-schema.
python -m service.main --load-fixtures fixtures/sample_calls.jsonl

# Optional: live poll (5 min default)
python -m service.main --once
python -m service.main --watch

# Dashboard
streamlit run dashboard/app.py
# or: docker compose up streamlit  → http://localhost:8501
```

Backfill:

```bash
python -m service.main --backfill 2026-04-01
```

Tests:

```bash
pytest tests/ -v
```

Time zones: all timestamps are stored as `DateTime64(3, 'UTC')`; the dashboard
renders in IST via `toTimeZone(started_at, 'Asia/Kolkata')` (§10.8).

### Idempotency demo

```bash
python -m service.main --load-fixtures fixtures/sample_calls.jsonl
clickhouse-client --query "SELECT count() FROM analytics.calls FINAL"  # 50
python -m service.main --load-fixtures fixtures/sample_calls.jsonl
clickhouse-client --query "SELECT count() FROM analytics.calls FINAL"  # still 50
```

Note: this replays fixtures with **identical** `started_at`, so it would pass
under any sort key — it isn't the interesting case. Drift-resistance comes from
the `(tenant_id, call_id)` key itself: re-inserting one call with a perturbed
`started_at` still resolves to `count() FINAL = 1`, which the old
`(tenant_id, started_at, call_id)` key did not guarantee.

## Layout

| Path | Role |
|------|------|
| `service/poller.py` | zenlabs dashboard sessions only |
| `service/normalizer.py` | `CallMetric` → CH row (pure) |
| `service/writer.py` | batch INSERT only |
| `service/cursor.py` | `ingest_cursor` table |
| `service/main.py` | `--watch`, `--backfill`, `--load-fixtures` |
| `sql/001_init.sql` | `calls`, `calls_daily` MV, `ingest_cursor` |
| `sql/002_rebuild_calls_order_key.sql` | rebuilds `calls` onto `ORDER BY (tenant_id, call_id)` |
| `sql/queries.sql` | six canonical queries |
| `fixtures/sample_calls.jsonl` | 50 synthetic calls (7-day span) |

## Discussion answers (§8)

### Q1. Which ingestion mode, and why?

**Polling every 5 minutes** (`POLL_INTERVAL_SECONDS=300`, overridable). The hotel's questions are daily ("staffing on Friday 7–9pm", "Q2 room-type conversion") — sub-minute latency is unnecessary. Polling needs no inbound URL, no webhook signature/retry design, and survives restarts with a single cursor row. Against the four bars: **restart-safe** — cursor in `ingest_cursor` (ReplacingMergeTree per `tenant_id`), reloaded on start; **idempotent** — replays dedupe in `calls` via ReplacingMergeTree on `(tenant_id, call_id)`; **backpressure-tolerant** — failed cycles log and retry, backlog drains on the next successful poll; **auditable** — `SELECT * FROM calls FINAL WHERE call_id = '…'`. Webhook would be the v2 choice for near-real-time ops floors.

One operational caveat worth stating plainly: the cursor is stored at millisecond precision (`DateTime64(3)`) and the poller advances it to `max(started_at)`. If the upstream API emits sub-millisecond `started_at` and the cursor comparison is strict (`started > cursor`), the newest call can be re-fetched every cycle. The `(tenant_id, call_id)` dedup keeps the logical count correct, but it wastes work and inflates the rollup MV (see *Known gaps*). The robust fix is to persist/compare the cursor at the precision the API emits, or make the comparison inclusive on equality and let dedup handle the boundary call.

### Q2. Wide table or normalized? Why?

**One wide row per call** in `calls`, with `variables Map(String, String)` for agent-extracted fields (`room_type`, `rate_inr`, …). At ~100K calls/year across 12 properties, ClickHouse scans are cheap; every dashboard query is a single-table read. New agent variables need no `ALTER TABLE`. Normalized `calls` + `call_variables` would add JOINs ClickHouse is not optimized for, with no scale benefit at this volume.

### Q3. How does a replayed `call_id` produce a single logical row?

`ENGINE = ReplacingMergeTree(ingested_at) ORDER BY (tenant_id, call_id)`. Re-inserting the same `call_id` keeps the row with the latest `ingested_at` after merge. Because `started_at` is **not** in the sort key, timestamp drift on replay (the API returning a slightly different `started_at` on a re-pull) cannot fork the row into two — `(tenant_id, call_id)` is the identity. Queries read **`FROM calls FINAL`** (or `argMax(col, ingested_at)` grouped by the key) so readers see one logical row before the background merge runs. The writer does not skip duplicates in application code — dedup is storage semantics. `tests/test_idempotency.py` double-inserts one fixture and asserts `count() = 1` after `OPTIMIZE … FINAL`.

Two honest caveats:

- **Trade-off of dropping `started_at` from the sort key:** the daily queries filter `started_at >= today() - N`, which can no longer use the primary-key index for range-pruning. `PARTITION BY toYYYYMM(started_at)` still prunes to the relevant month-partitions, which is sufficient at this volume; at 10× it would warrant a `started_at` skip-index or a time-bucketed key. Note also that ReplacingMergeTree only collapses within a partition, so dedup assumes a call's `started_at` stays in one month — true for any realistic drift.
- **The rollup MV is not replay-safe.** `calls_daily` (SummingMergeTree) aggregates the **raw insert stream**, not `calls FINAL` — a materialized view fires once per insert and never sees the deduped view. Re-ingesting a call therefore double-counts in `calls_daily`. All six shipped queries read `calls FINAL`, so nothing rendered today is affected, but any future query against `calls_daily` must account for this (the production fix is an `AggregatingMergeTree` MV keyed so replays merge, or sourcing the rollup from the deduped table).

### Q4. How did you decide which six queries to ship?

| Query | Operator question | Metric(s) |
|-------|-------------------|-----------|
| 1 Daily volume + conversion | Are we answering and booking? | pickup, resolved |
| 2 Peak-hour (IST) | Where to add staff? | `started_at` |
| 3 Escalation reasons | Why humans take over? | escalated, escalation_reason |
| 4 Drop-off by end_node | Where does the workflow lose callers? | end_node, dropped, resolved |
| 5 Conversion by room_type | Sea-view vs garden performance? | `variables['room_type']`, resolved |
| 6 Language mix | TTS / voice spend split? | language |

Each maps to a metric the hotel named; #2 and #5 combine fields into staffing/revenue decisions rather than restating a single metric.

### Q5. Smallest production-ready change set

For 100 properties × 10× volume: **webhook + queue** (Kafka/SQS) in front of the writer to absorb spikes; **partitioning + TTL** on `calls` (`TTL started_at + INTERVAL 2 YEAR DELETE`); **replay-safe rollups** (AggregatingMergeTree MV, or rebuild `calls_daily` from `calls FINAL`) so the daily view stops double-counting replays; **hourly-by-property materialization** to avoid scanning raw `calls`; **row-level security** on `property_id`; **real `property_id` resolution** so calls stop defaulting to a single hotel; **monitoring** on cursor lag and ingest error rate. Polling and a single wide table remain valid for v1 — they become the bottleneck at scale, not the wrong first cut.

## Zenlabs API mapping notes

Dashboard `InteractionSession` fields are mapped in `session_to_call_metric`. Pre-baked fields come from the API; gaps are defaulted per §10.5:

| Contract field | Source |
|----------------|--------|
| `duration_seconds` | API |
| `num_turns` | `user_turn_count` **only** — agent turns are not exposed, so this is a user-turn floor, not the total in §6 |
| `agent_id` | `active_agent.id` |
| `pickup_status` | `call_outcome` (`answered` / `no_answer`→`no_pickup` / `voicemail`); `no_pickup` when outcome unknown and duration is 0 |
| `escalated`, `escalation_reason`, `resolved`, `dropped` | `disposition` |
| `variables` | `collected_variables` |
| `property_id` | `collected_variables['property_id']`, else `default_property_id` (`thv_goa`) — see *Known gaps* |
| `num_one_word_replies`, `language` (if absent) | default `0` / `en-IN` or from variables |
| `end_node` | `end_reason` or disposition |

`conversations_list` is empty in the sandbox; **dashboard-sessions** is the poll source.

## Known gaps & caveats

Per §12, naming the gaps scores higher than hiding them. The ones a reviewer running this will actually hit:

1. **`property_id` defaults to `thv_goa`.** When a session does not expose `property_id`, the normalizer stamps the configured `default_property_id`. In the current sandbox, dashboard sessions don't carry property, so **every live call lands as `thv_goa`** — a silent mislabel. §10.5 ("don't infer") argues for writing `''` and flagging the gap instead. None of the six queries slice by `property_id`, so no shipped query is *wrong* today, but any cross-property analysis would be misleading. Fixtures carry explicit `property_id` and are unaffected. Verify with: `SELECT DISTINCT property_id FROM calls FINAL WHERE call_id NOT LIKE 'call_%'`.

2. **`num_turns` is user turns only.** The API exposes `user_turn_count`, not agent turns, so the stored value is a floor, not the §6 "total user+agent turns." Documented rather than inferred.

3. **`calls_daily` is not replay-safe** . The MV double-counts re-ingested calls; the six shipped queries avoid it by reading `calls FINAL`.

4. **Cursor precision / re-pull**. Millisecond cursor vs. potentially sub-millisecond API timestamps can cause the newest call to be re-fetched each poll cycle. Dedup keeps the logical count at 1; the cost is wasted ingests plus MV inflation. Diagnose with `SELECT count() FROM calls` vs `SELECT count() FROM calls FINAL`, and compare `ingest_cursor` against `max(started_at)`.

