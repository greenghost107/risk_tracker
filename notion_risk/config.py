"""Load and validate .env configuration (PRD §4).

Never falls back to a default account size: a wrong denominator would
silently corrupt every risk figure in the table.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import dotenv_values

REQUIRED_KEYS = ("NOTION_URL", "NOTION_TOKEN", "ACCOUNT_SIZE")


class ConfigError(Exception):
    """Missing, empty, or invalid .env value. Always exit code 1."""

    exit_code = 1


@dataclass
class Config:
    notion_url: str
    notion_token: str
    account_size: Decimal


def _load_raw(env_path: Path) -> dict[str, str]:
    # Real environment variables first -- this is how hosted platforms
    # (e.g. Streamlit Community Cloud "Secrets") deliver config, since there
    # is no .env file on disk there. A local .env file, if present, overrides
    # them, which keeps local development working exactly as before.
    raw = {k.upper(): v for k, v in os.environ.items()}
    file_values = dotenv_values(env_path)
    raw.update({k.upper(): v for k, v in file_values.items() if k is not None and v is not None})
    # Keys are matched case-insensitively so `notion_url` and `NOTION_URL`
    # are treated the same; the last-seen value for a given uppercased key wins.
    return raw


def load_config(env_path: Path | str = ".env") -> Config:
    env_path = Path(env_path)
    raw = _load_raw(env_path)

    for key in REQUIRED_KEYS:
        if not raw.get(key, "").strip():
            raise ConfigError(f"missing or empty required config key: {key}")

    account_size_str = raw["ACCOUNT_SIZE"].strip()
    try:
        account_size = Decimal(account_size_str)
    except InvalidOperation as exc:
        raise ConfigError(f"ACCOUNT_SIZE is not a valid number: '{account_size_str}'") from exc
    if account_size <= 0:
        raise ConfigError(f"ACCOUNT_SIZE must be a positive number, got: {account_size}")

    return Config(
        notion_url=raw["NOTION_URL"].strip(),
        notion_token=raw["NOTION_TOKEN"].strip(),
        account_size=account_size,
    )


def load_config_or_exit(env_path: Path | str = ".env") -> Config:
    try:
        return load_config(env_path)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        sys.exit(exc.exit_code)
