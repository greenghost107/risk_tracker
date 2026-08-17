from decimal import Decimal

import pytest

from notion_risk.config import ConfigError, load_config


def write_env(tmp_path, content: str):
    path = tmp_path / ".env"
    path.write_text(content, encoding="utf-8")
    return path


def test_load_config_happy_path(tmp_path):
    path = write_env(
        tmp_path,
        "NOTION_URL=https://notion.so/Week-abc123\n"
        "NOTION_TOKEN=ntn_secret\n"
        "ACCOUNT_SIZE=25000\n",
    )
    config = load_config(path)
    assert config.notion_url == "https://notion.so/Week-abc123"
    assert config.notion_token == "ntn_secret"
    assert config.account_size == Decimal("25000")


def test_load_config_falls_back_to_environment_variables(tmp_path, monkeypatch):
    # No .env file at all -- mirrors a hosted platform (e.g. Streamlit
    # Community Cloud "Secrets") that exposes config via os.environ instead.
    monkeypatch.setenv("NOTION_URL", "https://notion.so/Week-abc123")
    monkeypatch.setenv("NOTION_TOKEN", "ntn_secret")
    monkeypatch.setenv("ACCOUNT_SIZE", "18000")

    config = load_config(tmp_path / "nonexistent.env")

    assert config.notion_url == "https://notion.so/Week-abc123"
    assert config.notion_token == "ntn_secret"
    assert config.account_size == Decimal("18000")


def test_load_config_env_file_overrides_environment_variables(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTION_URL", "https://notion.so/from-env-var")
    monkeypatch.setenv("NOTION_TOKEN", "ntn_from_env_var")
    monkeypatch.setenv("ACCOUNT_SIZE", "1")

    path = write_env(
        tmp_path,
        "NOTION_URL=https://notion.so/from-file\n"
        "NOTION_TOKEN=ntn_from_file\n"
        "ACCOUNT_SIZE=25000\n",
    )
    config = load_config(path)

    assert config.notion_url == "https://notion.so/from-file"
    assert config.notion_token == "ntn_from_file"
    assert config.account_size == Decimal("25000")


def test_load_config_is_case_insensitive_for_keys(tmp_path):
    path = write_env(
        tmp_path,
        "notion_url=https://notion.so/Week-abc123\n"
        "notion_token=ntn_secret\n"
        "account_size=18000\n",
    )
    config = load_config(path)
    assert config.notion_url == "https://notion.so/Week-abc123"
    assert config.account_size == Decimal("18000")


@pytest.mark.parametrize("missing_key", ["NOTION_URL", "NOTION_TOKEN", "ACCOUNT_SIZE"])
def test_load_config_missing_key_raises(tmp_path, missing_key):
    keys = {
        "NOTION_URL": "https://notion.so/Week-abc123",
        "NOTION_TOKEN": "ntn_secret",
        "ACCOUNT_SIZE": "25000",
    }
    del keys[missing_key]
    content = "\n".join(f"{k}={v}" for k, v in keys.items())
    path = write_env(tmp_path, content)
    with pytest.raises(ConfigError, match=missing_key):
        load_config(path)


def test_load_config_empty_value_raises(tmp_path):
    path = write_env(
        tmp_path,
        "NOTION_URL=https://notion.so/Week-abc123\n"
        "NOTION_TOKEN=\n"
        "ACCOUNT_SIZE=25000\n",
    )
    with pytest.raises(ConfigError, match="NOTION_TOKEN"):
        load_config(path)


def test_load_config_non_numeric_account_size_raises(tmp_path):
    path = write_env(
        tmp_path,
        "NOTION_URL=https://notion.so/Week-abc123\n"
        "NOTION_TOKEN=ntn_secret\n"
        "ACCOUNT_SIZE=not-a-number\n",
    )
    with pytest.raises(ConfigError, match="ACCOUNT_SIZE"):
        load_config(path)


@pytest.mark.parametrize("bad_value", ["0", "-1000"])
def test_load_config_non_positive_account_size_raises(tmp_path, bad_value):
    path = write_env(
        tmp_path,
        "NOTION_URL=https://notion.so/Week-abc123\n"
        "NOTION_TOKEN=ntn_secret\n"
        f"ACCOUNT_SIZE={bad_value}\n",
    )
    with pytest.raises(ConfigError, match="positive"):
        load_config(path)


def test_config_error_exit_code():
    assert ConfigError.exit_code == 1
