-- Six canonical daily queries for the Taj Group voice analytics stack.
-- Use FINAL on `calls` so ReplacingMergeTree dedupes replays at read time.

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Daily call volume + conversion (last 7 days)
--    Business: are we answering and closing reservations day over day?
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    toDate(started_at)                                             AS day,
    count()                                                        AS total_calls,
    countIf(pickup_status = 'answered')                            AS answered,
    countIf(resolved = 1)                                          AS resolved,
    round(resolved / nullIf(answered, 0) * 100, 1)                 AS conv_pct
FROM calls FINAL
WHERE tenant_id = {tenant:String}
  AND started_at >= today() - 7
GROUP BY day
ORDER BY day DESC;


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Peak-hour distribution (last 30 days, IST)
--    Business: staffing — how many calls land in each hour-of-day?
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    toHour(toTimeZone(started_at, 'Asia/Kolkata'))                 AS hour_ist,
    count()                                                        AS call_count
FROM calls FINAL
WHERE tenant_id = {tenant:String}
  AND started_at >= today() - 30
GROUP BY hour_ist
ORDER BY hour_ist;


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Escalation reason breakdown (last 30 days)
--    Business: why are calls leaving the agent to a human?
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    escalation_reason,
    count()                                                        AS escalations,
    round(count() * 100.0 / sum(count()) OVER (), 1)               AS pct_of_escalations
FROM calls FINAL
WHERE tenant_id = {tenant:String}
  AND started_at >= today() - 30
  AND escalated = 1
  AND escalation_reason != ''
GROUP BY escalation_reason
ORDER BY escalations DESC;


-- ─────────────────────────────────────────────────────────────────────────────
-- 4. Drop-off by end_node (last 30 days)
--    Business: which workflow nodes lose unresolved or dropped callers?
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    end_node,
    countIf(dropped = 1)                                           AS dropped_calls,
    countIf(resolved = 0 AND dropped = 0)                          AS unresolved_calls,
    count()                                                        AS total_at_node
FROM calls FINAL
WHERE tenant_id = {tenant:String}
  AND started_at >= today() - 30
  AND end_node != ''
GROUP BY end_node
ORDER BY dropped_calls + unresolved_calls DESC;


-- ─────────────────────────────────────────────────────────────────────────────
-- 5. Conversion by room type (agent variable bag)
--    Business: is sea-view under-converting vs garden?
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    variables['room_type']                                         AS room_type,
    count()                                                        AS total_calls,
    countIf(resolved = 1)                                          AS resolved,
    round(resolved / nullIf(count(), 0) * 100, 1)                  AS conv_pct
FROM calls FINAL
WHERE tenant_id = {tenant:String}
  AND started_at >= today() - 30
  AND variables['room_type'] != ''
GROUP BY room_type
ORDER BY total_calls DESC;


-- ─────────────────────────────────────────────────────────────────────────────
-- 6. Language mix (last 30 days)
--    Business: TTS / voice spend — share of en-IN vs hi-IN vs other
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    language,
    count()                                                        AS calls,
    round(count() * 100.0 / sum(count()) OVER (), 1)               AS pct
FROM calls FINAL
WHERE tenant_id = {tenant:String}
  AND started_at >= today() - 30
GROUP BY language
ORDER BY calls DESC;
