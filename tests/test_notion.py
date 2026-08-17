import requests
import pytest

from notion_risk.notion import (
    AuthError,
    InvalidUrlError,
    PageNotFoundError,
    RetryExhaustedError,
    extract_page_id,
    fetch_block_children,
    fetch_page,
    fetch_page_lines,
    flatten_blocks,
)


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.headers = headers or {}

    def json(self):
        return self._json_data


class FakeSession:
    """Returns queued responses/exceptions in order, one per .request() call."""

    def __init__(self, queue):
        self.queue = list(queue)
        self.calls = []

    def request(self, method, url, headers=None, params=None, timeout=None):
        self.calls.append((method, url, params))
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


PAGE_ID = "3bdff09e431480dc9716d92c74e6f87a"


# --- extract_page_id ------------------------------------------------------


@pytest.mark.parametrize(
    "url,expected_id",
    [
        (
            "https://app.notion.com/p/WW34-positions-3bdff09e431480dc9716d92c74e6f87a",
            "3bdff09e431480dc9716d92c74e6f87a",
        ),
        (
            "https://www.notion.so/Week-of-Aug-11-3bdff09e431480dc9716d92c74e6f87a",
            "3bdff09e431480dc9716d92c74e6f87a",
        ),
        (
            "https://www.notion.so/3bdff09e-4314-80dc-9716-d92c74e6f87a",
            "3bdff09e-4314-80dc-9716-d92c74e6f87a",
        ),
        (
            "https://www.notion.so/Week-3bdff09e431480dc9716d92c74e6f87a?v=abcdef0123456789abcdef0123456789",
            "3bdff09e431480dc9716d92c74e6f87a",
        ),
    ],
)
def test_extract_page_id(url, expected_id):
    assert extract_page_id(url) == expected_id


def test_extract_page_id_malformed_url_raises():
    with pytest.raises(InvalidUrlError):
        extract_page_id("https://example.com/not-a-notion-page")


def test_invalid_url_error_exit_code():
    assert InvalidUrlError.exit_code == 2


# --- fetch_page: hard-stop conditions --------------------------------------


def test_fetch_page_not_found_raises_404():
    session = FakeSession([FakeResponse(404)])
    with pytest.raises(PageNotFoundError):
        fetch_page(PAGE_ID, "token", session)


def test_fetch_page_archived_raises_even_with_200():
    # The API returns 200 for a trashed page; archived flag must be checked.
    session = FakeSession([FakeResponse(200, {"archived": True})])
    with pytest.raises(PageNotFoundError):
        fetch_page(PAGE_ID, "token", session)


def test_fetch_page_in_trash_raises_even_with_200():
    session = FakeSession([FakeResponse(200, {"in_trash": True})])
    with pytest.raises(PageNotFoundError):
        fetch_page(PAGE_ID, "token", session)


def test_fetch_page_401_raises_auth_error():
    session = FakeSession([FakeResponse(401)])
    with pytest.raises(AuthError):
        fetch_page(PAGE_ID, "token", session)


def test_fetch_page_403_raises_auth_error():
    session = FakeSession([FakeResponse(403)])
    with pytest.raises(AuthError):
        fetch_page(PAGE_ID, "token", session)


def test_page_not_found_exit_code():
    assert PageNotFoundError.exit_code == 3


def test_auth_error_exit_code():
    assert AuthError.exit_code == 4


# --- retry behavior ---------------------------------------------------------


def test_rate_limit_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr("notion_risk.notion.time.sleep", lambda *_: None)
    session = FakeSession([FakeResponse(429), FakeResponse(200, {"archived": False})])
    fetch_page(PAGE_ID, "token", session)  # no raise
    assert len(session.calls) == 2


def test_rate_limit_exhausts_after_three_attempts(monkeypatch):
    monkeypatch.setattr("notion_risk.notion.time.sleep", lambda *_: None)
    session = FakeSession([FakeResponse(429), FakeResponse(429), FakeResponse(429)])
    with pytest.raises(RetryExhaustedError):
        fetch_page(PAGE_ID, "token", session)
    assert len(session.calls) == 3


def test_server_error_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr("notion_risk.notion.time.sleep", lambda *_: None)
    session = FakeSession([FakeResponse(503), FakeResponse(200, {"archived": False})])
    fetch_page(PAGE_ID, "token", session)
    assert len(session.calls) == 2


def test_network_failure_retries_then_exhausts(monkeypatch):
    monkeypatch.setattr("notion_risk.notion.time.sleep", lambda *_: None)
    exc = requests.ConnectionError("boom")
    session = FakeSession([exc, exc, exc])
    with pytest.raises(RetryExhaustedError):
        fetch_page(PAGE_ID, "token", session)
    assert len(session.calls) == 3


def test_retry_exhausted_exit_code():
    assert RetryExhaustedError.exit_code == 5


# --- fetch_block_children: pagination ---------------------------------------


def test_fetch_block_children_paginates_until_exhausted():
    page1 = FakeResponse(200, {"results": [{"id": "a"}], "has_more": True, "next_cursor": "c2"})
    page2 = FakeResponse(200, {"results": [{"id": "b"}], "has_more": False, "next_cursor": None})
    session = FakeSession([page1, page2])
    blocks = fetch_block_children(PAGE_ID, "token", session)
    assert [b["id"] for b in blocks] == ["a", "b"]
    assert len(session.calls) == 2
    # second call must carry the cursor from the first page
    assert session.calls[1][2]["start_cursor"] == "c2"


# --- flatten_blocks: block types + one level of recursion -------------------


def _rt(text):
    return {"rich_text": [{"plain_text": text}]}


def test_flatten_blocks_reads_allowed_types_and_ignores_others():
    blocks = [
        {"type": "paragraph", "paragraph": _rt("NVT")},
        {"type": "bulleted_list_item", "bulleted_list_item": _rt("12 @ 162.2")},
        {"type": "divider", "divider": {}},  # not in ALLOWED_BLOCK_TYPES, ignored
        {"type": "heading_2", "heading_2": _rt("stop-loss: 158")},
    ]
    lines = flatten_blocks(blocks, "token", session=None)
    assert lines == ["NVT", "12 @ 162.2", "stop-loss: 158"]


def test_flatten_blocks_recurses_one_level_into_children():
    child_response = FakeResponse(
        200,
        {
            "results": [{"type": "paragraph", "paragraph": _rt("nested line")}],
            "has_more": False,
            "next_cursor": None,
        },
    )
    session = FakeSession([child_response])
    blocks = [
        {
            "type": "toggle",
            "toggle": {},
            "has_children": True,
            "id": "toggle-1",
        }
    ]
    lines = flatten_blocks(blocks, "token", session, depth=0)
    assert lines == ["nested line"]


def test_flatten_blocks_does_not_recurse_past_one_level():
    # depth=1 means we're already inside a recursed call; has_children here
    # must not trigger another fetch.
    session = FakeSession([])
    blocks = [{"type": "toggle", "toggle": {}, "has_children": True, "id": "x"}]
    lines = flatten_blocks(blocks, "token", session, depth=1)
    assert lines == []
    assert session.calls == []


# --- fetch_page_lines: full pipeline -----------------------------------------


def test_fetch_page_lines_end_to_end():
    url = f"https://www.notion.so/Week-{PAGE_ID}"
    page_resp = FakeResponse(200, {"archived": False})
    children_resp = FakeResponse(
        200,
        {
            "results": [{"type": "paragraph", "paragraph": _rt("NVT")}],
            "has_more": False,
            "next_cursor": None,
        },
    )
    session = FakeSession([page_resp, children_resp])
    lines = fetch_page_lines(url, "token", session)
    assert lines == ["NVT"]
