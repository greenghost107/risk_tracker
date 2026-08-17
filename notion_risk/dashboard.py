"""Pure helpers for the Streamlit dashboard: row status, cell styling, and
dataframe construction. Kept free of any `streamlit` import so it can be
unit tested without a running app.
"""

from __future__ import annotations

from enum import Enum, auto

import pandas as pd

from notion_risk.render import COLUMNS, build_display_row, build_totals_row
from notion_risk.risk import RiskRow, Totals

GREEN_STYLE = "background-color: #c6f6d5; color: #1a202c;"
RED_STYLE = "background-color: #fed7d7; color: #1a202c;"
NO_STYLE = ""


class RowStatus(Enum):
    OK = auto()  # dollar risk <= 0: stop at/above avg price, nothing left to lose
    AT_RISK = auto()  # dollar risk > 0: real exposure
    UNRESOLVED = auto()  # no stop-loss at all: risk is undefined, not zero


def row_status(row: RiskRow) -> RowStatus:
    if row.unresolved:
        return RowStatus.UNRESOLVED
    if row.dollar_risk <= 0:
        return RowStatus.OK
    return RowStatus.AT_RISK


def risk_cell_style(row: RiskRow) -> str:
    status = row_status(row)
    if status is RowStatus.OK:
        return GREEN_STYLE
    if status is RowStatus.AT_RISK:
        return RED_STYLE
    return NO_STYLE


def build_table_dataframe(rows: list[RiskRow], totals: Totals) -> pd.DataFrame:
    records = [build_display_row(row) for row in rows]
    records.append(build_totals_row(totals))
    return pd.DataFrame(records, columns=COLUMNS)


def style_table(df: pd.DataFrame, rows: list[RiskRow]) -> "pd.io.formats.style.Styler":
    """Color only the 'risk' cell of each position row. The totals row
    (the last row, one more than len(rows)) is never colored."""
    risk_col_index = list(df.columns).index("risk")

    def _highlight(row: pd.Series) -> list[str]:
        styles = [NO_STYLE] * len(row)
        row_index = row.name
        if row_index < len(rows):
            styles[risk_col_index] = risk_cell_style(rows[row_index])
        return styles

    return df.style.apply(_highlight, axis=1)


def unresolved_error_message(rows: list[RiskRow]) -> str | None:
    unresolved_symbols = [row.symbol for row in rows if row.unresolved]
    if not unresolved_symbols:
        return None
    return (
        f"No stop-loss set for: {', '.join(unresolved_symbols)} "
        "-- risk is undefined for these positions, not zero."
    )
