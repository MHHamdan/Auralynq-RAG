"""Notion connector — single **internal integration token**, no OAuth app.

The user creates an internal integration (notion.so/my-integrations), copies the
token, and shares the pages/databases they want indexed with it (page ••• →
Connections). Set ``AURALYNQ_CONNECTORS__NOTION_TOKEN`` (a Secret). We enumerate
shared pages via /v1/search, pull block text, and track ``last_edited_time`` as
the incremental cursor.
"""

from __future__ import annotations

import time

from auralynq.connectors.base import ConnectorDoc, ConnectorError
from auralynq.telemetry import get_logger
from auralynq.utils import content_hash

_log = get_logger("auralynq.connectors.notion")

_API = "https://api.notion.com/v1"
_VERSION = "2022-06-28"
_RATE_DELAY = 0.34  # ~3 req/s, Notion's average limit

# Block types whose rich_text we treat as document body.
_TEXT_BLOCKS = {
    "paragraph",
    "heading_1",
    "heading_2",
    "heading_3",
    "bulleted_list_item",
    "numbered_list_item",
    "to_do",
    "toggle",
    "quote",
    "callout",
    "code",
}


class NotionConnector:
    name = "notion"

    def __init__(self, token: str, *, max_pages: int = 200) -> None:
        self._token = token or ""
        self._max_pages = max_pages

    def configured(self) -> bool:
        return bool(self._token)

    def setup_hint(self) -> str:
        return (
            "Create an internal integration at notion.so/my-integrations, share your "
            "pages with it, and set AURALYNQ_CONNECTORS__NOTION_TOKEN."
        )

    # -- HTTP ---------------------------------------------------------------
    def _client(self):
        import httpx

        return httpx.Client(
            base_url=_API,
            timeout=20.0,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Notion-Version": _VERSION,
                "Content-Type": "application/json",
            },
        )

    def _post(self, client, path: str, json: dict) -> dict:
        time.sleep(_RATE_DELAY)
        r = client.post(path, json=json)
        if r.status_code == 401:
            raise ConnectorError("Notion token is invalid or the page isn't shared with the integration.")
        if r.status_code == 429:
            raise ConnectorError("Notion rate limit hit — try again shortly.")
        r.raise_for_status()
        return r.json()

    def _get(self, client, path: str, params: dict | None = None) -> dict:
        time.sleep(_RATE_DELAY)
        r = client.get(path, params=params or {})
        if r.status_code == 401:
            raise ConnectorError("Notion token is invalid or the page isn't shared with the integration.")
        r.raise_for_status()
        return r.json()

    # -- enumeration --------------------------------------------------------
    def _search_pages(self, client) -> list[dict]:
        pages: list[dict] = []
        cursor = None
        while len(pages) < self._max_pages:
            body: dict = {
                "filter": {"property": "object", "value": "page"},
                "sort": {"direction": "descending", "timestamp": "last_edited_time"},
                "page_size": 100,
            }
            if cursor:
                body["start_cursor"] = cursor
            data = self._post(client, "/search", body)
            pages.extend(data.get("results", []))
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
        return pages[: self._max_pages]

    # -- block text ---------------------------------------------------------
    @staticmethod
    def _rich(block: dict, key: str) -> str:
        rt = (block.get(key) or {}).get("rich_text", [])
        return "".join(seg.get("plain_text", "") for seg in rt)

    def _page_text(self, client, page_id: str, depth: int = 0) -> str:
        if depth > 3:
            return ""
        parts: list[str] = []
        cursor = None
        while True:
            params = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            data = self._get(client, f"/blocks/{page_id}/children", params)
            for blk in data.get("results", []):
                bt = blk.get("type")
                if bt in _TEXT_BLOCKS:
                    txt = self._rich(blk, bt)
                    if txt:
                        parts.append(txt)
                if blk.get("has_children"):
                    child = self._page_text(client, blk["id"], depth + 1)
                    if child:
                        parts.append(child)
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
        return "\n".join(parts)

    @staticmethod
    def _title_of(page: dict) -> str:
        props = page.get("properties", {})
        for prop in props.values():
            if prop.get("type") == "title":
                return "".join(t.get("plain_text", "") for t in prop.get("title", [])) or "Untitled"
        return "Untitled"

    # -- Connector API ------------------------------------------------------
    def list_changes(self, cursor: str | None) -> tuple[list[ConnectorDoc], str | None]:
        if not self.configured():
            raise ConnectorError("Notion token not set.")
        docs: list[ConnectorDoc] = []
        newest = cursor
        with self._client() as client:
            for page in self._search_pages(client):
                edited = page.get("last_edited_time")
                if cursor and edited and edited <= cursor:
                    continue  # results are newest-first → we can stop, but keep simple
                pid = page["id"]
                text = self._page_text(client, pid)
                if not text.strip():
                    continue
                docs.append(
                    ConnectorDoc(
                        id=pid,
                        source=f"notion://{pid}",
                        title=self._title_of(page),
                        text=text,
                        content_hash=content_hash(text),
                        authored_at=edited,
                        url=page.get("url"),
                        metadata={"last_edited_time": edited},
                    )
                )
                if edited and (newest is None or edited > newest):
                    newest = edited
        _log.info("notion.changes", count=len(docs), cursor=cursor)
        return docs, newest

    def list_ids(self) -> set[str] | None:
        if not self.configured():
            return None
        with self._client() as client:
            return {p["id"] for p in self._search_pages(client)}
