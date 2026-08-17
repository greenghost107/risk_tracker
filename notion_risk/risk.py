"""Decimal risk math over parsed positions, plus portfolio totals.

Uses decimal.Decimal throughout per PRD §7: float arithmetic on prices
produces visible cent-level drift in the risk columns. Rounding only
happens at display time (render.py), never here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from notion_risk.parser import ParsedPosition


@dataclass
class RiskRow:
    symbol: str
    avg_price: Decimal
    amount: Decimal
    pos_size: Decimal
    stop_loss: Decimal | None
    dollar_risk: Decimal | None
    risk_percentage: Decimal | None
    risk_for_position: Decimal | None
    risk: Decimal | None
    unresolved: bool
    locked_in_gain: bool  # stop at/above avg price: raised into profit, not exposure


@dataclass
class Totals:
    total_pos_size: Decimal
    total_pos_size_pct: Decimal
    total_risk_for_position: Decimal
    total_risk_pct: Decimal
    unresolved_count: int


def _weighted_avg_price(lots: list[tuple[Decimal, Decimal]]) -> Decimal:
    total_amount = sum(a for a, _ in lots)
    total_cost = sum(a * p for a, p in lots)
    return total_cost / total_amount


def compute_row(position: ParsedPosition) -> RiskRow:
    amount = sum(a for a, _ in position.lots)
    avg_price = _weighted_avg_price(position.lots)
    pos_size = avg_price * amount

    if position.stop_loss is None:
        return RiskRow(
            symbol=position.symbol,
            avg_price=avg_price,
            amount=amount,
            pos_size=pos_size,
            stop_loss=None,
            dollar_risk=None,
            risk_percentage=None,
            risk_for_position=None,
            risk=None,
            unresolved=True,
            locked_in_gain=False,
        )

    dollar_risk = avg_price - position.stop_loss
    risk_percentage = dollar_risk / avg_price
    risk_for_position = dollar_risk * amount
    locked_in_gain = dollar_risk < 0

    if locked_in_gain:
        # dollar_risk / risk_percentage stay signed (they show the cushion
        # a raised stop gives), but exposure figures can't go negative.
        risk_for_position = Decimal(0)

    return RiskRow(
        symbol=position.symbol,
        avg_price=avg_price,
        amount=amount,
        pos_size=pos_size,
        stop_loss=position.stop_loss,
        dollar_risk=dollar_risk,
        risk_percentage=risk_percentage,
        risk_for_position=risk_for_position,
        risk=None,  # filled in once account_size is known, by compute_rows
        unresolved=False,
        locked_in_gain=locked_in_gain,
    )


def compute_rows(positions: list[ParsedPosition], account_size: Decimal) -> list[RiskRow]:
    rows = [compute_row(p) for p in positions]
    for row in rows:
        if row.risk_for_position is not None:
            row.risk = row.risk_for_position / account_size
    return rows


def compute_totals(rows: list[RiskRow], account_size: Decimal) -> Totals:
    total_pos_size = sum((r.pos_size for r in rows), Decimal(0))
    total_pos_size_pct = total_pos_size / account_size

    heat_rows = [r for r in rows if not r.unresolved and not r.locked_in_gain]
    total_risk_for_position = sum((r.risk_for_position for r in heat_rows), Decimal(0))
    total_risk_pct = total_risk_for_position / account_size

    unresolved_count = sum(1 for r in rows if r.unresolved)

    return Totals(
        total_pos_size=total_pos_size,
        total_pos_size_pct=total_pos_size_pct,
        total_risk_for_position=total_risk_for_position,
        total_risk_pct=total_risk_pct,
        unresolved_count=unresolved_count,
    )
