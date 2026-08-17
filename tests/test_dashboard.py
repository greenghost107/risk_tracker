from decimal import Decimal

from notion_risk.dashboard import (
    GREEN_STYLE,
    NO_STYLE,
    RED_STYLE,
    RowStatus,
    build_table_dataframe,
    risk_cell_style,
    row_status,
    style_table,
    unresolved_error_message,
)
from notion_risk.parser import ParsedPosition
from notion_risk.risk import compute_row, compute_rows, compute_totals

ACCOUNT_SIZE = Decimal("25000")


def _row(symbol, lots, stop_loss):
    return compute_row(ParsedPosition(symbol=symbol, lots=lots, stop_loss=stop_loss))


# --- row_status / risk_cell_style -------------------------------------------


def test_row_status_at_risk_when_dollar_risk_positive():
    row = _row("AAA", [(Decimal("10"), Decimal("100"))], Decimal("95"))
    assert row_status(row) is RowStatus.AT_RISK
    assert risk_cell_style(row) == RED_STYLE


def test_row_status_ok_when_dollar_risk_negative():
    row = _row("BBB", [(Decimal("10"), Decimal("100"))], Decimal("105"))
    assert row_status(row) is RowStatus.OK
    assert risk_cell_style(row) == GREEN_STYLE


def test_row_status_ok_when_dollar_risk_exactly_zero():
    # stop exactly at avg price: breakeven, nothing left to lose -> green
    row = _row("CCC", [(Decimal("10"), Decimal("100"))], Decimal("100"))
    assert row.dollar_risk == Decimal("0")
    assert row_status(row) is RowStatus.OK
    assert risk_cell_style(row) == GREEN_STYLE


def test_row_status_unresolved_when_no_stop():
    row = _row("DDD", [(Decimal("10"), Decimal("100"))], None)
    assert row_status(row) is RowStatus.UNRESOLVED
    assert risk_cell_style(row) == NO_STYLE


# --- build_table_dataframe ----------------------------------------------------


def test_build_table_dataframe_includes_totals_row(load_fixture):
    from notion_risk.parser import parse_lines

    lines = load_fixture("risk_table_reference.txt")
    parsed = parse_lines(lines)
    rows = compute_rows(parsed.positions, ACCOUNT_SIZE)
    totals = compute_totals(rows, ACCOUNT_SIZE)

    df = build_table_dataframe(rows, totals)

    assert len(df) == len(rows) + 1
    assert df.iloc[-1]["symbol"] == "TOTAL"
    assert df.iloc[0]["symbol"] == "ASML"


# --- style_table ----------------------------------------------------------------


def test_style_table_colors_risk_cell_only_for_position_rows():
    rows = [
        _row("AAA", [(Decimal("10"), Decimal("100"))], Decimal("95")),  # red
        _row("BBB", [(Decimal("10"), Decimal("100"))], Decimal("105")),  # green
        _row("DDD", [(Decimal("10"), Decimal("100"))], None),  # unresolved, no color
    ]
    totals = compute_totals(rows, ACCOUNT_SIZE)
    df = build_table_dataframe(rows, totals)
    styler = style_table(df, rows)

    computed = styler._compute()
    risk_col_index = list(df.columns).index("risk")

    ctx = computed.ctx
    assert ctx[(0, risk_col_index)] == [("background-color", "#fed7d7"), ("color", "#1a202c")]
    assert ctx[(1, risk_col_index)] == [("background-color", "#c6f6d5"), ("color", "#1a202c")]
    # unresolved row: no style applied at all for its risk cell
    assert ctx.get((2, risk_col_index), []) == []
    # totals row (index 3): never colored
    assert ctx.get((3, risk_col_index), []) == []


# --- unresolved_error_message ----------------------------------------------------


def test_unresolved_error_message_none_when_all_resolved():
    rows = [_row("AAA", [(Decimal("10"), Decimal("100"))], Decimal("95"))]
    assert unresolved_error_message(rows) is None


def test_unresolved_error_message_lists_symbols():
    rows = [
        _row("AAA", [(Decimal("10"), Decimal("100"))], Decimal("95")),
        _row("BBB", [(Decimal("5"), Decimal("50"))], None),
        _row("CCC", [(Decimal("2"), Decimal("20"))], None),
    ]
    message = unresolved_error_message(rows)
    assert message is not None
    assert "BBB" in message
    assert "CCC" in message
    assert "AAA" not in message
