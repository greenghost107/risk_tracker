"""Notion API access: URL -> page ID, fetch, flatten to plain-text lines.

PRD §5. A `session` object can be injected (anything exposing a
`requests`-shaped `.request(method, url, headers=, params=, timeout=)`) so
this module is testable without a network call or a token.
"""

from __future__ import annotations

import re
import time

import requests

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
MAX_ATTEMPTS = 3

ALLOWED_BLOCK_TYPES = {
    "paragraph",
    "bulleted_list_item",
    "numbered_list_item",
    "to_do",
    "heading_1",
    "heading_2",
    "heading_3",
    "quote",
    "code",
}

_PAGE_ID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    r"|[0-9a-fA-F]{32}"
)


class NotionError(Exception):
    exit_code = 1


class InvalidUrlError(NotionError):
    exit_code = 2


class PageNotFoundError(NotionError):
    exit_code = 3


class AuthError(NotionError):
    exit_code = 4


class RetryExhaustedError(NotionError):
    exit_code = 5


def extract_page_id(url: str) -> str:
    """Pull the 32-char page ID out of a Notion URL.

    Accepts the dashed UUID form and the undashed form appended to a slug.
    The query string (e.g. `?v=...`) is stripped first so a view ID in it
    can't be mistaken for the page ID.
    """
    url_without_query = url.split("?", 1)[0]
    match = _PAGE_ID_RE.search(url_without_query)
    if not match:
        raise InvalidUrlError(f"could not find a page ID in NOTION_URL: '{url}'")
    return match.group(0)


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION}


def _request_with_retry(session, method: str, url: str, *, headers: dict, **kwargs):
    backoff = 1.0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = session.request(method, url, headers=headers, timeout=10, **kwargs)
        except requests.RequestException as exc:
            if attempt == MAX_ATTEMPTS:
                raise RetryExhaustedError(
                    f"network failure after {MAX_ATTEMPTS} attempts: {exc}"
                ) from exc
            time.sleep(backoff)
            backoff *= 2
            continue

        if response.status_code == 429:
            if attempt == MAX_ATTEMPTS:
                raise RetryExhaustedError(f"rate limited after {MAX_ATTEMPTS} attempts (HTTP 429)")
            retry_after = float(response.headers.get("Retry-After", backoff))
            time.sleep(retry_after)
            backoff *= 2
            continue

        if 500 <= response.status_code < 600:
            if attempt == MAX_ATTEMPTS:
                raise RetryExhaustedError(
                    f"server error after {MAX_ATTEMPTS} attempts: HTTP {response.status_code}"
                )
            time.sleep(backoff)
            backoff *= 2
            continue

        return response

    raise AssertionError("unreachable: loop always returns or raises")


def _raise_for_common_errors(response, page_id: str) -> None:
    if response.status_code == 404:
        raise PageNotFoundError(f"page not found or not shared with the integration: {page_id}")
    if response.status_code == 401:
        raise AuthError("bad or expired NOTION_TOKEN")
    if response.status_code == 403:
        raise AuthError("integration lacks read capability for this page")


def fetch_page(page_id: str, token: str, session=None) -> dict:
    session = session or requests
    response = _request_with_retry(
        session, "GET", f"{NOTION_API_BASE}/pages/{page_id}", headers=_headers(token)
    )
    _raise_for_common_errors(response, page_id)
    page = response.json()
    # The API returns 200 for a trashed page, so "deleted" won't surface as
    # a 404 -- the archived/in_trash flag must be checked explicitly.
    if page.get("archived") or page.get("in_trash"):
        raise PageNotFoundError(f"page is archived/deleted: {page_id}")
    return page


def fetch_block_children(block_id: str, token: str, session=None) -> list[dict]:
    session = session or requests
    blocks: list[dict] = []
    cursor = None
    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        response = _request_with_retry(
            session,
            "GET",
            f"{NOTION_API_BASE}/blocks/{block_id}/children",
            headers=_headers(token),
            params=params,
        )
        _raise_for_common_errors(response, block_id)
        data = response.json()
        blocks.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return blocks


def _extract_text(block: dict) -> str | None:
    block_type = block.get("type")
    if block_type not in ALLOWED_BLOCK_TYPES:
        return None
    data = block.get(block_type, {})
    rich_text = data.get("rich_text", [])
    return "".join(rt.get("plain_text", "") for rt in rich_text)


def flatten_blocks(blocks: list[dict], token: str, session=None, depth: int = 0) -> list[str]:
    """Flatten block content into plain-text lines, recursing one level into
    blocks with children (toggles, nested lists) but no deeper."""
    lines: list[str] = []
    for block in blocks:
        text = _extract_text(block)
        if text is not None:
            lines.append(text)
        if block.get("has_children") and depth == 0:
            children = fetch_block_children(block["id"], token, session)
            lines.extend(flatten_blocks(children, token, session, depth=depth + 1))
    return lines


def fetch_page_lines(url: str, token: str, session=None) -> list[str]:
    """Full Stage 1 pipeline: URL -> page ID -> existence check -> flattened lines."""
    page_id = extract_page_id(url)
    fetch_page(page_id, token, session)
    blocks = fetch_block_children(page_id, token, session)
    return flatten_blocks(blocks, token, session)
