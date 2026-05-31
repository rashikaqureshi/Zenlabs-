"""Streamlit dashboard — six canonical queries as cards (IST display)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from service.clickhouse_client import get_client
from service.config import settings

TENANT = settings.tenant_id

st.set_page_config(page_title="Hotel Voice Analytics", layout="wide")
st.title("Taj Group — Voice Agent Analytics")
st.caption(f"Tenant: `{TENANT}` · times in IST · reads `calls FINAL`")

client = get_client()


def q(sql: str) -> pd.DataFrame:
    result = client.query(sql, parameters={"tenant": TENANT})
    return pd.DataFrame(result.result_rows, columns=result.column_names)


# ── 1. Daily volume + conversion (7d) ────────────────────────────────────────
st.subheader("1. Daily call volume + conversion (last 7 days)")
df1 = q(
    """
    SELECT
        toDate(toTimeZone(started_at, 'Asia/Kolkata')) AS day,
        count() AS total_calls,
        countIf(pickup_status = 'answered') AS answered,
        countIf(resolved = 1) AS resolved,
        round(resolved / nullIf(answered, 0) * 100, 1) AS conv_pct
    FROM calls FINAL
    WHERE tenant_id = {tenant:String}
      AND started_at >= today() - 7
    GROUP BY day
    ORDER BY day
    """
)
st.dataframe(df1, use_container_width=True)
if not df1.empty:
    st.line_chart(df1.set_index("day")[["total_calls", "resolved"]])

st.divider()

# ── 2. Peak-hour staffing (30d, IST) ─────────────────────────────────────────
st.subheader("2. Peak-hour distribution (last 30 days, IST)")
df2 = q(
    """
    SELECT
        toHour(toTimeZone(started_at, 'Asia/Kolkata')) AS hour_ist,
        count() AS call_count
    FROM calls FINAL
    WHERE tenant_id = {tenant:String}
      AND started_at >= today() - 30
    GROUP BY hour_ist
    ORDER BY hour_ist
    """
)
st.bar_chart(df2.set_index("hour_ist")["call_count"] if not df2.empty else df2)

st.divider()

# ── 3. Escalation reasons ────────────────────────────────────────────────────
st.subheader("3. Escalation reason breakdown (last 30 days)")
df3 = q(
    """
    SELECT
        escalation_reason,
        count() AS escalations,
        round(count() * 100.0 / sum(count()) OVER (), 1) AS pct
    FROM calls FINAL
    WHERE tenant_id = {tenant:String}
      AND started_at >= today() - 30
      AND escalated = 1
      AND escalation_reason != ''
    GROUP BY escalation_reason
    ORDER BY escalations DESC
    """
)
col_a, col_b = st.columns(2)
with col_a:
    st.dataframe(df3, use_container_width=True)
with col_b:
    if not df3.empty:
        st.bar_chart(df3.set_index("escalation_reason")["escalations"])

st.divider()

# ── 4. Drop-off by end_node ──────────────────────────────────────────────────
st.subheader("4. Drop-off by workflow end_node (last 30 days)")
df4 = q(
    """
    SELECT
        end_node,
        countIf(dropped = 1) AS dropped_calls,
        countIf(resolved = 0 AND dropped = 0) AS unresolved_calls,
        count() AS total_at_node
    FROM calls FINAL
    WHERE tenant_id = {tenant:String}
      AND started_at >= today() - 30
      AND end_node != ''
    GROUP BY end_node
    ORDER BY dropped_calls + unresolved_calls DESC
    """
)
st.dataframe(df4, use_container_width=True)

st.divider()

# ── 5. Conversion by room type ───────────────────────────────────────────────
st.subheader("5. Conversion by room type (last 30 days)")
df5 = q(
    """
    SELECT
        variables['room_type'] AS room_type,
        count() AS total_calls,
        countIf(resolved = 1) AS resolved,
        round(resolved / nullIf(count(), 0) * 100, 1) AS conv_pct
    FROM calls FINAL
    WHERE tenant_id = {tenant:String}
      AND started_at >= today() - 30
      AND variables['room_type'] != ''
    GROUP BY room_type
    ORDER BY total_calls DESC
    """
)
st.dataframe(df5, use_container_width=True)
if not df5.empty:
    st.bar_chart(df5.set_index("room_type")["conv_pct"])

st.divider()

# ── 6. Language mix ──────────────────────────────────────────────────────────
st.subheader("6. Language mix (last 30 days)")
df6 = q(
    """
    SELECT
        language,
        count() AS calls,
        round(count() * 100.0 / sum(count()) OVER (), 1) AS pct
    FROM calls FINAL
    WHERE tenant_id = {tenant:String}
      AND started_at >= today() - 30
    GROUP BY language
    ORDER BY calls DESC
    """
)
col_c, col_d = st.columns(2)
with col_c:
    st.dataframe(df6, use_container_width=True)
with col_d:
    if not df6.empty:
        st.bar_chart(df6.set_index("language")["calls"])
