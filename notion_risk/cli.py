"""argparse entry point: wires config -> fetch -> parse -> compute -> render."""

from __future__ import annotations

import argparse
import sys

from notion_risk.config import ConfigError, load_config
from notion_risk.notion import NotionError, fetch_page_lines
from notion_risk.parser import ParseError, classify_line, parse_lines
from notion_risk.render import render_console_table, sort_rows, write_csv, write_json
from notion_risk.risk import compute_rows, compute_totals


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="risk-tracker",
        description="Read the week's Notion positions page and print a portfolio risk table.",
    )
    parser.add_argument("--csv", metavar="PATH", help="also write unrounded rows to a CSV file")
    parser.add_argument("--json", metavar="PATH", help="also write structured output to a JSON file")
    parser.add_argument(
        "--sort",
        choices=["page", "risk", "size"],
        default="page",
        help="row order: page (default, order of appearance), risk, or size",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="echo each classified line with its class, for debugging a page that parses oddly",
    )
    parser.add_argument(
        "--env-file",
        metavar="PATH",
        default=".env",
        help="path to the .env file (default: .env in the current directory)",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_arg_parser().parse_args(argv)


def _echo_classification(lines: list[str]) -> None:
    print("Line classification:")
    for line_no, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        line_class, _ = classify_line(line)
        print(f"  {line_no:>4}  {line_class.name:<13} {line!r}")
    print()


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        config = load_config(args.env_file)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return exc.exit_code

    try:
        lines = fetch_page_lines(config.notion_url, config.notion_token)
    except NotionError as exc:
        print(f"Notion fetch error: {exc}", file=sys.stderr)
        return exc.exit_code

    if args.verbose:
        _echo_classification(lines)

    try:
        parsed = parse_lines(lines)
    except ParseError as exc:
        print(f"Parse error: {exc}", file=sys.stderr)
        return exc.exit_code

    rows = compute_rows(parsed.positions, config.account_size)
    rows = sort_rows(rows, args.sort)
    totals = compute_totals(rows, config.account_size)

    print(render_console_table(rows, totals, parsed.warnings))

    if args.csv:
        write_csv(rows, totals, args.csv)
    if args.json:
        write_json(rows, totals, parsed.warnings, args.json)

    return 0


def main() -> None:
    sys.exit(run())
