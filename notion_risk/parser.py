"""Line-oriented state machine that turns flattened Notion text into positions.

Operates on a plain ``list[str]`` with no Notion types in its signature, so it
is testable from fixtures without a network call or a token.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum, auto


class LineClass(Enum):
    BLANK = auto()
    INITIAL_STOP = auto()
    STOP = auto()
    LOT = auto()
    SYMBOL = auto()
    NOISE = auto()


_INITIAL_STOP_RE = re.compile(r"^initial\s+stop[-\s]?loss\s*:", re.IGNORECASE)
_STOP_RE = re.compile(r"^stop[-\s]?loss\s*:\s*\$?([\d,]*\.?\d+)?", re.IGNORECASE)
_LOT_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*@\s*\$?([\d,]*\.?\d+)")
_SYMBOL_RE = re.compile(r"^[A-Z][A-Z.\-]{0,6}$")
# A standalone numeric token, e.g. "186.42" or "1,397.86" -- but not digits
# embedded in a word like "ema20" or "sma200" (no \w boundary around them),
# which are indicator names in a note, not a price someone meant to record.
_STANDALONE_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)*\b")


class ParseError(Exception):
    """A hard-stop parse condition (PRD §6). Always exit code 6."""

    exit_code = 6


@dataclass
class ParsedPosition:
    symbol: str
    lots: list[tuple[Decimal, Decimal]]
    stop_loss: Decimal | None  # None means the group was never closed


@dataclass
class ParseResult:
    positions: list[ParsedPosition] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def classify_line(line: str) -> tuple[LineClass, re.Match | None]:
    """Classify a single trimmed line using the PRD §6 rule order."""
    if line == "":
        return LineClass.BLANK, None
    match = _INITIAL_STOP_RE.match(line)
    if match:
        return LineClass.INITIAL_STOP, match
    match = _STOP_RE.match(line)
    if match:
        return LineClass.STOP, match
    match = _LOT_RE.match(line)
    if match:
        return LineClass.LOT, match
    match = _SYMBOL_RE.match(line)
    if match:
        return LineClass.SYMBOL, match
    return LineClass.NOISE, None


def _parse_decimal(raw: str) -> Decimal:
    return Decimal(raw.replace(",", ""))


class _Parser:
    def __init__(self) -> None:
        self.positions: list[ParsedPosition] = []
        self.warnings: list[str] = []
        self.seen_symbols: set[str] = set()
        self.current_symbol: str | None = None
        self.open_lots: list[tuple[Decimal, Decimal]] = []

    def _flush_open_group(self, line_no: int) -> None:
        """Close the open group as unresolved, if it has any lots."""
        if not self.open_lots:
            return
        self.positions.append(
            ParsedPosition(symbol=self.current_symbol, lots=self.open_lots, stop_loss=None)
        )
        self.warnings.append(
            f"line {line_no}: {self.current_symbol} has {len(self.open_lots)} lot(s) "
            "with no closing stop-loss; emitted unresolved"
        )
        self.open_lots = []

    def _handle_symbol(self, line: str, line_no: int) -> None:
        self._flush_open_group(line_no)
        if line in self.seen_symbols:
            raise ParseError(f"line {line_no}: duplicate symbol heading '{line}'")
        self.seen_symbols.add(line)
        self.current_symbol = line
        self.open_lots = []

    def _handle_lot(self, match: re.Match, line: str, line_no: int) -> None:
        if self.current_symbol is None:
            raise ParseError(f"line {line_no}: lot line before any symbol heading: '{line}'")
        amount_str, price_str = match.group(1), match.group(2)
        if "." in amount_str:
            raise ParseError(
                f"line {line_no}: fractional share amount not allowed: '{line}'"
            )
        self.open_lots.append((_parse_decimal(amount_str), _parse_decimal(price_str)))

    def _handle_stop(self, match: re.Match, line_no: int) -> None:
        price_str = match.group(1)
        if not price_str:
            self.warnings.append(
                f"line {line_no}: empty stop-loss for {self.current_symbol}; group stays open"
            )
            return
        if not self.open_lots:
            self.warnings.append(
                f"line {line_no}: stop-loss for {self.current_symbol} with no preceding lots; ignored"
            )
            return
        self.positions.append(
            ParsedPosition(
                symbol=self.current_symbol,
                lots=self.open_lots,
                stop_loss=_parse_decimal(price_str),
            )
        )
        self.open_lots = []

    def _handle_noise(self, line: str, line_no: int) -> None:
        if _STANDALONE_NUMBER_RE.search(line):
            self.warnings.append(f"line {line_no}: unparseable numeric-looking line: '{line}'")

    def run(self, lines: list[str]) -> ParseResult:
        for line_no, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            line_class, match = classify_line(line)
            if line_class is LineClass.BLANK or line_class is LineClass.INITIAL_STOP:
                continue
            if line_class is LineClass.STOP:
                self._handle_stop(match, line_no)
            elif line_class is LineClass.LOT:
                self._handle_lot(match, line, line_no)
            elif line_class is LineClass.SYMBOL:
                self._handle_symbol(line, line_no)
            else:
                self._handle_noise(line, line_no)
        self._flush_open_group(len(lines) + 1)
        return ParseResult(positions=self.positions, warnings=self.warnings)


def parse_lines(lines: list[str]) -> ParseResult:
    """Parse flattened Notion text lines into positions plus warnings.

    Raises ParseError on the two hard-stop conditions from PRD §6: a lot
    line before any symbol heading, and a duplicate symbol heading.
    """
    return _Parser().run(lines)
