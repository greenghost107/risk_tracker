"""Table / CSV / JSON rendering of computed risk rows (PRD §8).

Rounding happens here and only here: prices and dollar amounts to 2dp,
percentages to 2dp with a `%` suffix. CSV output is the exception -- it
gets unrounded values for spreadsheet use.
"""

from __future__ import annotations

import csv
import io
import json
from decimal import Decimal
from pathlib import Path

from rich import box
from rich.console import Console
from rich.table import Table

from notion_risk.risk import RiskRow, Totals

COLUMNS = [
    "symbol",
    "avg price",
    "amount",
    "pos size",
    "stop loss",
    "dollar risk",
    "risk percentage",
    "$ risk for position",
    "risk",
]

VALID_SORT_KEYS = ("page", "risk", "size")

LOCKED_IN_GAIN_LEGEND = "* stop raised above avg price -- locked-in gain, excluded from portfolio heat"


def _fmt_decimal(value: Decimal | None, places: int = 2) -> str:
    if value is None:
        return ""
    return str(value.quantize(Decimal(1).scaleb(-places)))


def _fmt_percentage(value: Decimal | None, places: int = 2) -> str:
    if value is None:
        return ""
    return f"{(value * 100).quantize(Decimal(1).scaleb(-places))}%"


def sort_rows(rows: list[RiskRow], sort_key: str) -> list[RiskRow]:
    if sort_key not in VALID_SORT_KEYS:
        raise ValueError(f"invalid sort key: '{sort_key}' (must be one of {VALID_SORT_KEYS})")
    if sort_key == "page":
        return list(rows)
    if sort_key == "risk":
        return sorted(rows, key=lambda r: r.risk if r.risk is not None else Decimal("-Infinity"), reverse=True)
    return sorted(rows, key=lambda r: r.pos_size, reverse=True)


def build_display_row(row: RiskRow) -> dict[str, str]:
    symbol = row.symbol + ("*" if row.locked_in_gain else "")
    return {
        "symbol": symbol,
        "avg price": _fmt_decimal(row.avg_price),
        "amount": _fmt_decimal(row.amount),
        "pos size": _fmt_decimal(row.pos_size),
        "stop loss": _fmt_decimal(row.stop_loss),
        "dollar risk": _fmt_decimal(row.dollar_risk),
        "risk percentage": _fmt_percentage(row.risk_percentage),
        "$ risk for position": _fmt_decimal(row.risk_for_position),
        "risk": _fmt_percentage(row.risk),
    }


def build_totals_row(totals: Totals) -> dict[str, str]:
    return {
        "symbol": "TOTAL",
        "avg price": "",
        "amount": "",
        "pos size": f"{_fmt_decimal(totals.total_pos_size)} ({_fmt_percentage(totals.total_pos_size_pct)})",
        "stop loss": "",
        "dollar risk": "",
        "risk percentage": "",
        "$ risk for position": _fmt_decimal(totals.total_risk_for_position),
        "risk": _fmt_percentage(totals.total_risk_pct),
    }


def unique_symbol_count(rows: list[RiskRow]) -> int:
    """Count distinct symbols, since a symbol split across separately-closed
    stop-losses (e.g. a partial exit) legitimately produces multiple rows."""
    return len({row.symbol for row in rows})


def summary_line(rows: list[RiskRow], totals: Totals) -> str:
    return (
        f"{unique_symbol_count(rows)} symbols, {len(rows)} entries, "
        f"{totals.unresolved_count} unresolved, "
        f"portfolio heat {_fmt_percentage(totals.total_risk_pct)}"
    )


def render_console_table(rows: list[RiskRow], totals: Totals, warnings: list[str]) -> str:
    # ASCII box-drawing: rich's default Unicode borders aren't encodable on
    # a default Windows console (cp1252), and this table is meant to print
    # cleanly to any terminal without relying on stdout being reconfigured.
    table = Table(show_header=True, header_style="bold", box=box.ASCII)
    for col in COLUMNS:
        table.add_column(col)
    for row in rows:
        display = build_display_row(row)
        table.add_row(*(display[col] for col in COLUMNS))
    totals_display = build_totals_row(totals)
    table.add_row(*(totals_display[col] for col in COLUMNS), style="bold")

    console = Console(file=io.StringIO(), width=120)
    console.print(table)
    if any(row.locked_in_gain for row in rows):
        console.print(LOCKED_IN_GAIN_LEGEND)
    if warnings:
        console.print("\nWarnings:")
        for warning in warnings:
            console.print(f"  - {warning}")
    console.print(summary_line(rows, totals))
    return console.file.getvalue()


def write_csv(rows: list[RiskRow], totals: Totals, path: str | Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        for row in rows:
            writer.writerow(
                [
                    row.symbol + ("*" if row.locked_in_gain else ""),
                    row.avg_price,
                    row.amount,
                    row.pos_size,
                    row.stop_loss if row.stop_loss is not None else "",
                    row.dollar_risk if row.dollar_risk is not None else "",
                    row.risk_percentage if row.risk_percentage is not None else "",
                    row.risk_for_position if row.risk_for_position is not None else "",
                    row.risk if row.risk is not None else "",
                ]
            )
        writer.writerow(
            [
                "TOTAL",
                "",
                "",
                totals.total_pos_size,
                "",
                "",
                "",
                totals.total_risk_for_position,
                totals.total_risk_pct,
            ]
        )


def _row_to_json_dict(row: RiskRow) -> dict:
    return {
        "symbol": row.symbol,
        "avg_price": str(row.avg_price),
        "amount": str(row.amount),
        "pos_size": str(row.pos_size),
        "stop_loss": str(row.stop_loss) if row.stop_loss is not None else None,
        "dollar_risk": str(row.dollar_risk) if row.dollar_risk is not None else None,
        "risk_percentage": str(row.risk_percentage) if row.risk_percentage is not None else None,
        "risk_for_position": str(row.risk_for_position) if row.risk_for_position is not None else None,
        "risk": str(row.risk) if row.risk is not None else None,
        "unresolved": row.unresolved,
        "locked_in_gain": row.locked_in_gain,
    }


def write_json(
    rows: list[RiskRow], totals: Totals, warnings: list[str], path: str | Path
) -> None:
    payload = {
        "positions": [_row_to_json_dict(row) for row in rows],
        "totals": {
            "total_pos_size": str(totals.total_pos_size),
            "total_pos_size_pct": str(totals.total_pos_size_pct),
            "total_risk_for_position": str(totals.total_risk_for_position),
            "total_risk_pct": str(totals.total_risk_pct),
            "unresolved_count": totals.unresolved_count,
        },
        "warnings": warnings,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
