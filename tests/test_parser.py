from decimal import Decimal

import pytest

from notion_risk.parser import LineClass, ParseError, classify_line, parse_lines


# --- classification -----------------------------------------------------


@pytest.mark.parametrize(
    "line,expected",
    [
        ("", LineClass.BLANK),
        ("initial stop-loss: 156", LineClass.INITIAL_STOP),
        ("initial stop loss: 180", LineClass.INITIAL_STOP),
        ("initial stop-loss:", LineClass.INITIAL_STOP),
        ("stop-loss: 98", LineClass.STOP),
        ("stop loss: 98", LineClass.STOP),
        ("stop-loss:", LineClass.STOP),
        ("12 @ 162.2", LineClass.LOT),
        ("10@100.5", LineClass.LOT),
        ("NVT", LineClass.SYMBOL),
        ("ASML", LineClass.SYMBOL),
        ("stop loss - ema20 - 186.42", LineClass.NOISE),
        ("adjusted stop-loss: 144.96", LineClass.NOISE),
        ("some data", LineClass.NOISE),
        ("stop loss follows ema20", LineClass.NOISE),
    ],
)
def test_classify_line(line, expected):
    line_class, _ = classify_line(line)
    assert line_class is expected


def test_initial_stop_tested_before_stop():
    # If STOP were tested first, this would be misclassified as STOP with
    # the "initial " prefix left dangling — order in classify_line matters.
    line_class, _ = classify_line("initial stop-loss: 156")
    assert line_class is LineClass.INITIAL_STOP


# --- reference page (PRD §6 worked check, concretized) -------------------


def test_reference_synthetic_worked_check(load_fixture):
    lines = load_fixture("reference_synthetic.txt")
    result = parse_lines(lines)
    assert [p.symbol for p in result.positions] == ["AAA", "AAA", "BBB", "CCC"]

    aaa1, aaa2, bbb, ccc = result.positions

    assert aaa1.lots == [(Decimal("10"), Decimal("100"))]
    assert aaa1.stop_loss == Decimal("98")

    assert aaa2.lots == [(Decimal("5"), Decimal("110"))]
    assert aaa2.stop_loss == Decimal("105")

    assert bbb.lots == [(Decimal("20"), Decimal("50")), (Decimal("15"), Decimal("52"))]
    assert bbb.stop_loss == Decimal("48")

    assert ccc.lots == [(Decimal("8"), Decimal("200"))]
    assert ccc.stop_loss == Decimal("190")

    assert result.warnings == []


def test_informal_notes_reference_page(load_fixture):
    # Structurally mirrors a real weekly Notion page (informal stop notes
    # without a colon, an "adjusted stop-loss:" NOISE line, etc.) with
    # fabricated symbols/prices, since the real page isn't fit for a public
    # test fixture.
    lines = load_fixture("informal_notes_synthetic.txt")
    result = parse_lines(lines)
    symbols = [p.symbol for p in result.positions]
    assert symbols == ["AAAA", "BBBB", "CCCC", "DDDD", "EEEE", "FFFF", "GGGG", "HHHH"]

    aaaa, bbbb, cccc, dddd, eeee, ffff, gggg, hhhh = result.positions

    # AAAA and BBBB both have informal stop notes ("stop loss - ema20 - X",
    # "stop-loss - ema20 - X") that don't match the strict STOP pattern
    # (no colon immediately after "stop loss"), so they never close.
    assert aaaa.stop_loss is None
    assert aaaa.lots == [(Decimal("12"), Decimal("50")), (Decimal("3"), Decimal("55"))]

    assert bbbb.stop_loss is None
    assert bbbb.lots == [(Decimal("21"), Decimal("30"))]

    # CCCC's "adjusted stop-loss:" line is NOISE (doesn't start with "stop"),
    # so both lots accumulate into one group closed by the real stop-loss.
    assert cccc.stop_loss == Decimal("38")
    assert cccc.lots == [(Decimal("12"), Decimal("40")), (Decimal("3"), Decimal("41"))]

    assert dddd.stop_loss == Decimal("21")
    assert dddd.lots == [(Decimal("34"), Decimal("20"))]

    assert eeee.stop_loss == Decimal("97")
    assert eeee.lots == [(Decimal("6"), Decimal("100")), (Decimal("6"), Decimal("99"))]

    assert ffff.stop_loss == Decimal("65")
    assert gggg.stop_loss == Decimal("23")
    assert hhhh.stop_loss == Decimal("290")

    # 2 unresolved groups (AAAA, BBBB) -> 2 warnings about them, plus the
    # numeric-looking noise lines that were silently dropped by classify_line.
    unresolved_warnings = [w for w in result.warnings if "unresolved" in w or "no closing" in w]
    assert len(unresolved_warnings) == 2


# --- individual documented edge cases ------------------------------------


def test_empty_stop_loss_keeps_group_open_then_closes(load_fixture):
    lines = load_fixture("empty_stop.txt")
    result = parse_lines(lines)
    assert len(result.positions) == 1
    pos = result.positions[0]
    assert pos.symbol == "DDD"
    assert pos.stop_loss == Decimal("48")
    assert pos.lots == [(Decimal("10"), Decimal("50"))]
    assert any("empty stop-loss" in w for w in result.warnings)


def test_lots_with_no_stop_at_all_flush_unresolved(load_fixture):
    lines = load_fixture("no_stop_at_all.txt")
    result = parse_lines(lines)
    assert len(result.positions) == 1
    pos = result.positions[0]
    assert pos.symbol == "EEE"
    assert pos.stop_loss is None
    assert pos.lots == [(Decimal("12"), Decimal("75"))]
    assert any("unresolved" in w for w in result.warnings)


def test_initial_stop_populated_and_empty_both_ignored(load_fixture):
    lines = load_fixture("initial_stop_variants.txt")
    result = parse_lines(lines)
    assert len(result.positions) == 2
    row1, row2 = result.positions
    assert row1.lots == [(Decimal("10"), Decimal("60"))]
    assert row1.stop_loss == Decimal("58")
    assert row2.lots == [(Decimal("5"), Decimal("62"))]
    assert row2.stop_loss == Decimal("59")
    # initial stop-loss lines never produce warnings, populated or empty
    assert result.warnings == []


def test_unequal_lot_sizes_prove_weighted_not_simple_mean(load_fixture):
    lines = load_fixture("unequal_lots.txt")
    result = parse_lines(lines)
    pos = result.positions[0]
    assert pos.lots == [(Decimal("10"), Decimal("100")), (Decimal("90"), Decimal("200"))]
    total_amount = sum(a for a, _ in pos.lots)
    weighted_avg = sum(a * p for a, p in pos.lots) / total_amount
    simple_mean = sum(p for _, p in pos.lots) / len(pos.lots)
    assert weighted_avg == Decimal("190")
    assert simple_mean == Decimal("150")
    assert weighted_avg != simple_mean


def test_lot_line_with_no_space_around_at(load_fixture):
    lines = load_fixture("lot_no_space.txt")
    result = parse_lines(lines)
    pos = result.positions[0]
    assert pos.lots == [(Decimal("10"), Decimal("100.5"))]


def test_prices_with_thousands_separator(load_fixture):
    lines = load_fixture("thousands_separator.txt")
    result = parse_lines(lines)
    pos = result.positions[0]
    assert pos.lots == [(Decimal("1"), Decimal("1397.86"))]
    assert pos.stop_loss == Decimal("1393.00")


def test_stop_above_avg_price_is_legal(load_fixture):
    lines = load_fixture("stop_above_avg.txt")
    result = parse_lines(lines)
    pos = result.positions[0]
    assert pos.stop_loss == Decimal("105")
    assert pos.lots == [(Decimal("10"), Decimal("100"))]
    # parser doesn't judge the sign, that's risk.py's job; no error/warning here
    assert result.warnings == []


def test_noise_line_with_digits_only_inside_a_word_does_not_warn(load_fixture):
    # "ema20" is an indicator name, not a price -- must not trigger the
    # "unparseable numeric-looking line" warning.
    lines = load_fixture("noise_with_indicator_name.txt")
    result = parse_lines(lines)
    pos = result.positions[0]
    assert pos.lots == [(Decimal("10"), Decimal("50"))]
    assert pos.stop_loss == Decimal("48")
    assert result.warnings == []


@pytest.mark.parametrize(
    "line",
    [
        "stop loss - ema20 - 186.42",  # standalone price-looking number
        "adjusted stop-loss: 144.96",
        "risk: 2%",
    ],
)
def test_noise_line_with_standalone_number_does_warn(line):
    result = parse_lines(["ZZZ", "1 @ 100", line, "stop-loss: 95"])
    assert any("unparseable numeric-looking line" in w for w in result.warnings)


@pytest.mark.parametrize(
    "line",
    [
        "stop loss follows ema20",
        "trailing sma200 stop",
        "some data",
        "stop loss at gapup AVWAP",
    ],
)
def test_noise_line_without_standalone_number_does_not_warn(line):
    result = parse_lines(["ZZZ", "1 @ 100", line, "stop-loss: 95"])
    assert result.warnings == []


# --- hard-stop error conditions (exit code 6) ----------------------------


def test_lot_before_symbol_raises(load_fixture):
    lines = load_fixture("lot_before_symbol.txt")
    with pytest.raises(ParseError, match="before any symbol heading"):
        parse_lines(lines)


def test_duplicate_symbol_raises(load_fixture):
    lines = load_fixture("duplicate_symbol.txt")
    with pytest.raises(ParseError, match="duplicate symbol heading"):
        parse_lines(lines)


def test_fractional_share_amount_raises(load_fixture):
    lines = load_fixture("fractional_shares.txt")
    with pytest.raises(ParseError, match="fractional share amount"):
        parse_lines(lines)


def test_parse_error_exit_code():
    assert ParseError.exit_code == 6
