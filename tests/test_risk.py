from decimal import Decimal

from notion_risk.parser import ParsedPosition, parse_lines
from notion_risk.risk import compute_row, compute_rows, compute_totals


def q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def pct2(value: Decimal) -> Decimal:
    return (value * 100).quantize(Decimal("0.01"))


# --- PRD §7 illustrative output, reproduced end to end --------------------


def test_risk_table_reference_matches_prd_illustrative_output(load_fixture):
    lines = load_fixture("risk_table_reference.txt")
    parsed = parse_lines(lines)
    account_size = Decimal("25000")
    rows = compute_rows(parsed.positions, account_size)

    expected = {
        "ASML": dict(avg="1397.86", amount="1", pos="1397.86", stop="1393.00",
                     dollar_risk="4.86", risk_pct="0.35", risk_for_pos="4.86", risk="0.02"),
        "NVT": dict(avg="114.62", amount="10", pos="1146.20", stop="112.39",
                    dollar_risk="2.23", risk_pct="1.95", risk_for_pos="22.30", risk="0.09"),
        "BKV": dict(avg="30.11", amount="40", pos="1204.40", stop="29.31",
                    dollar_risk="0.80", risk_pct="2.66", risk_for_pos="32.00", risk="0.13"),
        "VIK": dict(avg="74.82", amount="16", pos="1197.12", stop="72.26",
                    dollar_risk="2.56", risk_pct="3.42", risk_for_pos="40.96", risk="0.16"),
        "WBI": dict(avg="26.01", amount="40", pos="1040.40", stop="25.47",
                    dollar_risk="0.54", risk_pct="2.08", risk_for_pos="21.60", risk="0.09"),
        "Q": dict(avg="118.30", amount="4", pos="473.20", stop="111.02",
                  dollar_risk="7.28", risk_pct="6.15", risk_for_pos="29.12", risk="0.12"),
    }

    assert [r.symbol for r in rows] == list(expected)

    for row in rows:
        exp = expected[row.symbol]
        assert q2(row.avg_price) == Decimal(exp["avg"])
        assert row.amount == Decimal(exp["amount"])
        assert q2(row.pos_size) == Decimal(exp["pos"])
        assert q2(row.stop_loss) == Decimal(exp["stop"])
        assert q2(row.dollar_risk) == Decimal(exp["dollar_risk"])
        assert pct2(row.risk_percentage) == Decimal(exp["risk_pct"])
        assert q2(row.risk_for_position) == Decimal(exp["risk_for_pos"])
        assert pct2(row.risk) == Decimal(exp["risk"])

    totals = compute_totals(rows, account_size)
    assert q2(totals.total_pos_size) == Decimal("6459.18")
    assert q2(totals.total_risk_for_position) == Decimal("150.84")
    assert pct2(totals.total_risk_pct) == Decimal("0.60")
    assert totals.unresolved_count == 0


# --- targeted unit behavior -----------------------------------------------


def test_compute_row_share_weighted_average():
    position = ParsedPosition(
        symbol="GGG",
        lots=[(Decimal("10"), Decimal("100")), (Decimal("90"), Decimal("200"))],
        stop_loss=Decimal("180"),
    )
    row = compute_row(position)
    assert row.avg_price == Decimal("190")
    assert row.amount == Decimal("100")
    assert row.pos_size == Decimal("19000")


def test_compute_row_unresolved_has_blank_risk_columns():
    position = ParsedPosition(
        symbol="EEE",
        lots=[(Decimal("12"), Decimal("75"))],
        stop_loss=None,
    )
    row = compute_row(position)
    assert row.unresolved is True
    assert row.avg_price == Decimal("75")
    assert row.amount == Decimal("12")
    assert row.pos_size == Decimal("900")
    assert row.stop_loss is None
    assert row.dollar_risk is None
    assert row.risk_percentage is None
    assert row.risk_for_position is None
    assert row.risk is None


def test_compute_row_stop_above_avg_price_is_locked_in_gain():
    position = ParsedPosition(
        symbol="JJJ",
        lots=[(Decimal("10"), Decimal("100"))],
        stop_loss=Decimal("105"),
    )
    row = compute_row(position)
    assert row.locked_in_gain is True
    # dollar_risk / risk_percentage stay signed (cushion above breakeven)...
    assert row.dollar_risk == Decimal("-5")
    assert row.risk_percentage == Decimal("-0.05")
    # ...but exposure figures floor at 0, never negative.
    assert row.risk_for_position == Decimal("0")


def test_totals_exclude_unresolved_and_locked_in_gain_from_heat():
    account_size = Decimal("10000")
    positions = [
        ParsedPosition("AAA", [(Decimal("10"), Decimal("100"))], Decimal("95")),  # normal risk
        ParsedPosition("BBB", [(Decimal("5"), Decimal("50"))], None),  # unresolved
        ParsedPosition("CCC", [(Decimal("2"), Decimal("20"))], Decimal("25")),  # locked-in gain
    ]
    rows = compute_rows(positions, account_size)
    totals = compute_totals(rows, account_size)

    # heat total should only include AAA: (100-95)*10 = 50
    assert totals.total_risk_for_position == Decimal("50")
    assert totals.unresolved_count == 1

    # pos size total includes all three rows regardless of stop status
    expected_pos_size = Decimal("1000") + Decimal("250") + Decimal("40")
    assert totals.total_pos_size == expected_pos_size

    # CCC is locked-in gain: exposure floors at 0 rather than going negative
    ccc = next(r for r in rows if r.symbol == "CCC")
    assert ccc.dollar_risk == Decimal("-5")  # still signed, shows the cushion
    assert ccc.risk_for_position == Decimal("0")
    assert ccc.risk == Decimal("0")
