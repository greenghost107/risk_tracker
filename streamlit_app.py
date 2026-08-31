"""Streamlit dashboard for the Notion position risk table.

Live data only: on load (and on Refresh) this pulls straight from a Notion
page -- seeded from `.env` but editable in the UI, since the page URL
changes weekly while the token doesn't -- running the same fetch -> parse
-> compute pipeline as `main.py`. See notion_risk/dashboard.py for the pure
row-status / styling logic this renders.
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

DEFAULT_ACCOUNT_SIZE_SEED = 10_000.0

try:
    # ACCOUNT_SIZE and NOTION_URL are both optional here (unlike the CLI):
    # this dashboard has its own inputs for them below, so the app shouldn't
    # refuse to boot just because .env / secrets don't have them set.
    # NOTION_TOKEN never changes week to week, so it's still required.
    config = load_config(require_account_size=False, require_notion_url=False)
except ConfigError as exc:
    st.error(f"Config error: {exc}")
    st.stop()

if "lines" not in st.session_state:
    st.session_state.lines = None
    st.session_state.fetch_error = None

# Both seeded from .env / secrets on first load only; after that each
# widget's own session-state entry is the source of truth, so edits survive
# reruns (sorting, refreshing) without snapping back to the seed.
if "account_size" not in st.session_state:
    st.session_state.account_size = (
        float(config.account_size) if config.account_size is not None else DEFAULT_ACCOUNT_SIZE_SEED
    )
if "notion_url" not in st.session_state:
    st.session_state.notion_url = config.notion_url or ""

st.text_input(
    "Notion page URL",
    key="notion_url",
    placeholder="https://www.notion.so/Week-of-...",
    help="Set NOTION_URL in .env / secrets to change the starting value; edits here just apply for this session.",
)
notion_url = st.session_state.notion_url.strip()

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
        help="Set ACCOUNT_SIZE in .env / secrets to change the starting value; edits here just apply for this session.",
    )

account_size = Decimal(str(st.session_state.account_size))

if not notion_url:
    st.info("Enter a Notion page URL above to fetch positions.")
    st.stop()

if refresh_clicked or st.session_state.lines is None:
    st.session_state.fetch_error = None
    try:
        with st.spinner("Fetching Notion page..."):
            st.session_state.lines = fetch_page_lines(notion_url, config.notion_token)
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
