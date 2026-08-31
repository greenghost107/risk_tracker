"""Load and validate .env configuration (PRD §4).

The CLI never falls back to a default account size or page URL: a wrong
denominator would silently corrupt every risk figure in the table, and a
stale URL would silently read the wrong week's page. The Streamlit
dashboard is the exception -- it has its own account-size and page-URL
inputs in the UI, so ACCOUNT_SIZE and NOTION_URL there are just optional
seed values (pass require_account_size=False / require_notion_url=False),
not hard requirements to boot the app. NOTION_TOKEN never changes week to
week, so it stays required in both.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import dotenv_values

REQUIRED_KEYS = ("NOTION_TOKEN",)


class ConfigError(Exception):
    """Missing, empty, or invalid .env value. Always exit code 1."""

    exit_code = 1


@dataclass
class Config:
    notion_url: str | None
    notion_token: str
    account_size: Decimal | None


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


def load_config(
    env_path: Path | str = ".env",
    *,
    require_account_size: bool = True,
    require_notion_url: bool = True,
) -> Config:
    env_path = Path(env_path)
    raw = _load_raw(env_path)

    for key in REQUIRED_KEYS:
        if not raw.get(key, "").strip():
            raise ConfigError(f"missing or empty required config key: {key}")

    notion_url_str = raw.get("NOTION_URL", "").strip()
    notion_url: str | None
    if not notion_url_str:
        if require_notion_url:
            raise ConfigError("missing or empty required config key: NOTION_URL")
        notion_url = None
    else:
        notion_url = notion_url_str

    account_size_str = raw.get("ACCOUNT_SIZE", "").strip()
    account_size: Decimal | None
    if not account_size_str:
        if require_account_size:
            raise ConfigError("missing or empty required config key: ACCOUNT_SIZE")
        account_size = None
    else:
        try:
            account_size = Decimal(account_size_str)
        except InvalidOperation as exc:
            raise ConfigError(f"ACCOUNT_SIZE is not a valid number: '{account_size_str}'") from exc
        if account_size <= 0:
            raise ConfigError(f"ACCOUNT_SIZE must be a positive number, got: {account_size}")

    return Config(
        notion_url=notion_url,
        notion_token=raw["NOTION_TOKEN"].strip(),
        account_size=account_size,
    )


def load_config_or_exit(
    env_path: Path | str = ".env",
    *,
    require_account_size: bool = True,
    require_notion_url: bool = True,
) -> Config:
    try:
        return load_config(
            env_path,
            require_account_size=require_account_size,
            require_notion_url=require_notion_url,
        )
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        sys.exit(exc.exit_code)
