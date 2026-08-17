from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture():
    def _load(name: str) -> list[str]:
        text = (FIXTURES_DIR / name).read_text(encoding="utf-8")
        return text.splitlines()

    return _load
