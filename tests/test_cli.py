from decimal import Decimal

from notion_risk import cli
from notion_risk.config import Config, ConfigError
from notion_risk.notion import InvalidUrlError, PageNotFoundError


REFERENCE_LINES = [
    "ASML",
    "1 @ 1397.86",
    "stop-loss: 1393.00",
    "NVT",
    "10 @ 114.62",
    "stop-loss: 112.39",
]

FAKE_CONFIG = Config(
    notion_url="https://notion.so/whatever",
    notion_token="ntn_fake",
    account_size=Decimal("25000"),
)


def test_run_happy_path_returns_zero(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_config", lambda path: FAKE_CONFIG)
    monkeypatch.setattr(cli, "fetch_page_lines", lambda url, token: REFERENCE_LINES)

    exit_code = cli.run([])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "ASML" in out
    assert "2 symbols, 2 entries, 0 unresolved" in out


def test_run_writes_csv_and_json_when_requested(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "load_config", lambda path: FAKE_CONFIG)
    monkeypatch.setattr(cli, "fetch_page_lines", lambda url, token: REFERENCE_LINES)
    csv_path = tmp_path / "out.csv"
    json_path = tmp_path / "out.json"

    exit_code = cli.run(["--csv", str(csv_path), "--json", str(json_path)])

    assert exit_code == 0
    assert csv_path.exists()
    assert json_path.exists()


def test_run_verbose_echoes_classification(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_config", lambda path: FAKE_CONFIG)
    monkeypatch.setattr(cli, "fetch_page_lines", lambda url, token: REFERENCE_LINES)

    exit_code = cli.run(["--verbose"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "SYMBOL" in out
    assert "LOT" in out


def test_run_config_error_returns_its_exit_code(monkeypatch, capsys):
    def raise_config_error(path):
        raise ConfigError("missing ACCOUNT_SIZE")

    monkeypatch.setattr(cli, "load_config", raise_config_error)

    exit_code = cli.run([])

    assert exit_code == ConfigError.exit_code
    assert "ACCOUNT_SIZE" in capsys.readouterr().err


def test_run_notion_error_returns_its_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_config", lambda path: FAKE_CONFIG)

    def raise_notion_error(url, token):
        raise PageNotFoundError("page not found")

    monkeypatch.setattr(cli, "fetch_page_lines", raise_notion_error)

    exit_code = cli.run([])

    assert exit_code == PageNotFoundError.exit_code
    assert "page not found" in capsys.readouterr().err


def test_run_invalid_url_returns_its_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_config", lambda path: FAKE_CONFIG)

    def raise_invalid_url(url, token):
        raise InvalidUrlError("bad url")

    monkeypatch.setattr(cli, "fetch_page_lines", raise_invalid_url)

    exit_code = cli.run([])

    assert exit_code == InvalidUrlError.exit_code


def test_run_parse_error_returns_exit_code_six(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_config", lambda path: FAKE_CONFIG)
    monkeypatch.setattr(cli, "fetch_page_lines", lambda url, token: ["10 @ 100"])  # lot before symbol

    exit_code = cli.run([])

    assert exit_code == 6
    assert "before any symbol" in capsys.readouterr().err


def test_run_sort_flag_changes_row_order(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_config", lambda path: FAKE_CONFIG)
    monkeypatch.setattr(cli, "fetch_page_lines", lambda url, token: REFERENCE_LINES)

    exit_code = cli.run(["--sort", "size"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "ASML" in out and "NVT" in out
