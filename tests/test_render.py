import csv
import json
from decimal import Decimal

import pytest

from notion_risk.parser import parse_lines
from notion_risk.render import (
    build_display_row,
    build_totals_row,
    render_console_table,
    sort_rows,
    summary_line,
    unique_symbol_count,
    write_csv,
    write_json,
)
from notion_risk.risk import compute_rows, compute_totals


@pytest.fixture
def reference_rows_and_totals(load_fixture):
    lines = load_fixture("risk_table_reference.txt")
    parsed = parse_lines(lines)
    account_size = Decimal("25000")
    rows = compute_rows(parsed.positions, account_size)
    totals = compute_totals(rows, account_size)
    return rows, totals, parsed.warnings


def test_build_display_row_formats_and_rounds():
    lines = ["ASML", "1 @ 1397.86", "stop-loss: 1393.00"]
    parsed = parse_lines(lines)
    rows = compute_rows(parsed.positions, Decimal("25000"))
    display = build_display_row(rows[0])
    assert display["symbol"] == "ASML"
    assert display["avg price"] == "1397.86"
    assert display["stop loss"] == "1393.00"
    assert display["dollar risk"] == "4.86"
    assert display["risk percentage"] == "0.35%"
    assert display["risk"] == "0.02%"


def test_build_display_row_blank_for_unresolved():
    lines = ["EEE", "12 @ 75"]
    parsed = parse_lines(lines)
    rows = compute_rows(parsed.positions, Decimal("25000"))
    display = build_display_row(rows[0])
    assert display["stop loss"] == ""
    assert display["dollar risk"] == ""
    assert display["risk"] == ""
    # avg price / amount / pos size are still shown for unresolved rows
    assert display["avg price"] == "75.00"


def test_build_display_row_marks_locked_in_gain_with_trailing_star():
    lines = ["JJJ", "10 @ 100", "stop-loss: 105"]
    parsed = parse_lines(lines)
    rows = compute_rows(parsed.positions, Decimal("25000"))
    display = build_display_row(rows[0])
    assert display["symbol"] == "JJJ*"


def test_build_totals_row(reference_rows_and_totals):
    rows, totals, _ = reference_rows_and_totals
    display = build_totals_row(totals)
    assert display["symbol"] == "TOTAL"
    assert display["pos size"] == "6459.18 (25.84%)"
    assert display["$ risk for position"] == "150.84"
    assert display["risk"] == "0.60%"


def test_summary_line(reference_rows_and_totals):
    rows, totals, _ = reference_rows_and_totals
    assert summary_line(rows, totals) == "6 symbols, 6 entries, 0 unresolved, portfolio heat 0.60%"


def test_unique_symbol_count_collapses_a_symbol_split_across_two_stops():
    # OKTA closed by two separate stop-loss lines (e.g. a partial exit) is
    # correctly two rows, but only one unique symbol.
    lines = [
        "OKTA",
        "12 @ 148",
        "initial stop-loss: 139.97",
        "stop-loss: 144.96",
        "3 @ 150.13",
        "stop-loss: 146.87",
    ]
    parsed = parse_lines(lines)
    rows = compute_rows(parsed.positions, Decimal("25000"))
    assert len(rows) == 2
    assert unique_symbol_count(rows) == 1
    totals = compute_totals(rows, Decimal("25000"))
    assert summary_line(rows, totals) == "1 symbols, 2 entries, 0 unresolved, portfolio heat 0.19%"


# --- sorting ----------------------------------------------------------------


def test_sort_by_page_preserves_original_order(reference_rows_and_totals):
    rows, _, _ = reference_rows_and_totals
    sorted_rows = sort_rows(rows, "page")
    assert [r.symbol for r in sorted_rows] == [r.symbol for r in rows]


def test_sort_by_risk_descending(reference_rows_and_totals):
    rows, _, _ = reference_rows_and_totals
    sorted_rows = sort_rows(rows, "risk")
    risks = [r.risk for r in sorted_rows]
    assert risks == sorted(risks, reverse=True)
    assert sorted_rows[0].symbol == "VIK"  # highest $ risk for position / account size


def test_sort_by_size_descending(reference_rows_and_totals):
    rows, _, _ = reference_rows_and_totals
    sorted_rows = sort_rows(rows, "size")
    sizes = [r.pos_size for r in sorted_rows]
    assert sizes == sorted(sizes, reverse=True)
    assert sorted_rows[0].symbol == "ASML"  # largest pos size


def test_sort_rows_invalid_key_raises(reference_rows_and_totals):
    rows, _, _ = reference_rows_and_totals
    with pytest.raises(ValueError):
        sort_rows(rows, "bogus")


# --- csv / json output --------------------------------------------------------


def test_write_csv_unrounded_values(tmp_path, reference_rows_and_totals):
    rows, totals, _ = reference_rows_and_totals
    path = tmp_path / "out.csv"
    write_csv(rows, totals, path)

    with open(path, newline="", encoding="utf-8") as fh:
        reader = list(csv.reader(fh))

    assert reader[0] == list(build_totals_row(totals).keys()) or reader[0] == [
        "symbol", "avg price", "amount", "pos size", "stop loss",
        "dollar risk", "risk percentage", "$ risk for position", "risk",
    ]
    asml_row = reader[1]
    assert asml_row[0] == "ASML"
    assert asml_row[1] == "1397.86"
    total_row = reader[-1]
    assert total_row[0] == "TOTAL"
    assert Decimal(total_row[3]) == totals.total_pos_size


def test_write_json_structure(tmp_path, reference_rows_and_totals):
    rows, totals, warnings = reference_rows_and_totals
    path = tmp_path / "out.json"
    write_json(rows, totals, warnings, path)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["positions"]) == 6
    assert data["positions"][0]["symbol"] == "ASML"
    assert data["positions"][0]["avg_price"] == "1397.86"
    assert data["totals"]["unresolved_count"] == 0
    assert data["warnings"] == []


def test_write_json_unresolved_row_has_null_risk_fields(tmp_path):
    lines = ["EEE", "12 @ 75"]
    parsed = parse_lines(lines)
    rows = compute_rows(parsed.positions, Decimal("25000"))
    totals = compute_totals(rows, Decimal("25000"))
    path = tmp_path / "out.json"
    write_json(rows, totals, parsed.warnings, path)

    data = json.loads(path.read_text(encoding="utf-8"))
    row = data["positions"][0]
    assert row["stop_loss"] is None
    assert row["risk"] is None
    assert row["unresolved"] is True


# --- console table (smoke test) ----------------------------------------------


def test_render_console_table_contains_key_content(reference_rows_and_totals):
    rows, totals, warnings = reference_rows_and_totals
    output = render_console_table(rows, totals, warnings)
    assert "ASML" in output
    assert "TOTAL" in output
    assert "6 symbols, 6 entries, 0 unresolved" in output


def test_render_console_table_is_encodable_as_cp1252(reference_rows_and_totals):
    # Default Windows console codepage; rich's default Unicode box-drawing
    # characters aren't representable in it and previously raised
    # UnicodeEncodeError when printed there.
    rows, totals, warnings = reference_rows_and_totals
    output = render_console_table(rows, totals, warnings)
    output.encode("cp1252")  # must not raise


def test_render_console_table_shows_legend_when_locked_in_gain_present():
    lines = ["JJJ", "10 @ 100", "stop-loss: 105"]
    parsed = parse_lines(lines)
    rows = compute_rows(parsed.positions, Decimal("25000"))
    totals = compute_totals(rows, Decimal("25000"))
    output = render_console_table(rows, totals, parsed.warnings)
    assert "locked-in gain" in output
