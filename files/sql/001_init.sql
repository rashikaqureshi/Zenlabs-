-- ───────────────────────────────────────────── calls (raw, one row per call)

CREATE TABLE IF NOT EXISTS calls (
    call_id              String,
    tenant_id            LowCardinality(String),
    agent_id             LowCardinality(String),
    property_id          LowCardinality(String),  
    started_at           DateTime64(3, 'UTC'),
    ended_at             Nullable(DateTime64(3, 'UTC')),
    duration_seconds     UInt32,
    num_turns            UInt16,
    num_one_word_replies UInt16,
    escalated            UInt8,                   -- bool
    escalation_reason    LowCardinality(String), -- '' when not escalated
    dropped              UInt8,
    language             LowCardinality(String),  -- en-IN, hi-IN, en-US, …
    pickup_status        LowCardinality(String), -- answered, no_pickup, voicemail
    resolved             UInt8,
    end_node             LowCardinality(String),  -- last workflow node visited
    variables            Map(String, String),    -- agent-extracted, schema-free
    ingested_at          DateTime64(3, 'UTC') DEFAULT now64()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(started_at)
ORDER BY (tenant_id,started_at, call_id);


-- ───────────────────────────────────────────── daily rollup (materialized view)

CREATE MATERIALIZED VIEW IF NOT EXISTS calls_daily
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(day)
ORDER BY (tenant_id, property_id, day, language)
AS SELECT
    tenant_id,
    property_id,
    toDate(started_at) AS day,
    language,
    count() AS calls,
    countIf(pickup_status = 'answered') AS answered,
    countIf(resolved = 1) AS resolved,
    countIf(escalated = 1) AS escalated,
    countIf(dropped = 1) AS dropped,
    sum(duration_seconds) AS total_seconds
FROM calls
GROUP BY tenant_id, property_id, day, language;


-- ───────────────────────────────────────────── ingester cursor

CREATE TABLE IF NOT EXISTS ingest_cursor (
    tenant_id    LowCardinality(String),
    cursor_value DateTime64(3, 'UTC'),
    updated_at   DateTime64(3, 'UTC') DEFAULT now64()
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY tenant_id;
