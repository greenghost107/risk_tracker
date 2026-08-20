"""Streamlit dashboard for the Notion position risk table.

Live data only: on load (and on Refresh) this pulls straight from the
Notion page configured in `.env`, running the same config -> fetch ->
parse -> compute pipeline as `main.py`. See notion_risk/dashboard.py for
the pure row-status / styling logic this renders.
"""

from __future__ import annotations

from decimal import Decimal

import streamlit as st

from notion_risk.config import ConfigError, load_config
from notion_risk.dashboard import (
    build_table_dataframe,
    style_table,
    unresolved_error_message,
)
from notion_risk.notion import NotionError, fetch_page_lines
from notion_risk.parser import ParseError, parse_lines
from notion_risk.render import summary_line, sort_rows, unique_symbol_count
from notion_risk.risk import compute_rows, compute_totals

st.set_page_config(page_title="Risk Tracker", page_icon="\U0001F4CA", layout="wide")
st.title("Risk Tracker")

try:
    config = load_config()
except ConfigError as exc:
    st.error(f"Config error: {exc}")
    st.stop()

if "lines" not in st.session_state:
    st.session_state.lines = None
    st.session_state.fetch_error = None

# Seeded from .env / secrets on first load only; after that the widget's own
# session-state entry (key="account_size") is the source of truth, so edits
# survive reruns (sorting, refreshing) without snapping back to the .env value.
if "account_size" not in st.session_state:
    st.session_state.account_size = float(config.account_size)

refresh_col, sort_col, account_col = st.columns([1, 2, 2])
with refresh_col:
    refresh_clicked = st.button("Refresh from Notion", type="primary")
with sort_col:
    sort_key = st.selectbox("Sort by", ["page", "risk", "size"], index=0)
with account_col:
    st.number_input(
        "Account size ($)",
        min_value=0.01,
        step=100.0,
        format="%.2f",
        key="account_size",
    )

account_size = Decimal(str(st.session_state.account_size))

if refresh_clicked or st.session_state.lines is None:
    st.session_state.fetch_error = None
    try:
        with st.spinner("Fetching Notion page..."):
            st.session_state.lines = fetch_page_lines(config.notion_url, config.notion_token)
    except NotionError as exc:
        st.session_state.fetch_error = str(exc)

if st.session_state.fetch_error is not None:
    st.error(f"Notion fetch error: {st.session_state.fetch_error}")
    st.stop()

lines = st.session_state.lines
if lines is None:
    st.stop()

try:
    parsed = parse_lines(lines)
except ParseError as exc:
    st.error(f"Parse error: {exc}")
    st.stop()

rows = compute_rows(parsed.positions, account_size)
rows = sort_rows(rows, sort_key)
totals = compute_totals(rows, account_size)

heat_col, exposure_col, symbols_col, unresolved_col = st.columns(4)
heat_col.metric("Portfolio heat", f"{totals.total_risk_pct * 100:.2f}%")
exposure_col.metric("Exposure", f"{totals.total_pos_size_pct * 100:.2f}%")
symbols_col.metric(
    "Symbols", unique_symbol_count(rows), delta=f"{len(rows)} entries", delta_color="off"
)
unresolved_col.metric("Unresolved positions", totals.unresolved_count)

error_message = unresolved_error_message(rows)
if error_message:
    st.error(error_message)

df = build_table_dataframe(rows, totals)
styled = style_table(df, rows)
st.dataframe(styled, use_container_width=True, hide_index=True)

st.caption(summary_line(rows, totals))
st.caption("Green = no risk (stop at/above avg price). Red = still at risk. No color = unresolved, risk undefined.")

if parsed.warnings:
    with st.expander(f"Parser warnings ({len(parsed.warnings)})"):
        for warning in parsed.warnings:
            st.warning(warning)
