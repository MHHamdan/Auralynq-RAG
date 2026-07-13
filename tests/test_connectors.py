"""Cloud connectors — Notion/Slack/GDrive parse+cursor logic (mocked HTTP) and
the sync engine end-to-end on the offline stack (hash embedder + memory store)."""

from __future__ import annotations

import json

from auralynq.connectors.base import ConnectorDoc
from auralynq.connectors.gdrive import GDriveConnector
from auralynq.connectors.notion import NotionConnector
from auralynq.connectors.slack import SlackConnector
from auralynq.connectors.sync import load_state, sync_connector


class _Resp:
    def __init__(self, data, status=200):
        self._d = data
        self.status_code = status

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


# ── Notion ──────────────────────────────────────────────────────────────────


class _FakeNotion:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, path, json=None):
        if path == "/search":
            return _Resp(
                {
                    "results": [
                        {
                            "id": "p1",
                            "last_edited_time": "2026-07-12T10:00:00.000Z",
                            "url": "https://notion.so/p1",
                            "properties": {
                                "Name": {"type": "title", "title": [{"plain_text": "Roadmap"}]}
                            },
                        }
                    ],
                    "has_more": False,
                }
            )
        return _Resp({"results": [], "has_more": False})

    def get(self, path, params=None):
        if path.startswith("/blocks/"):
            return _Resp(
                {
                    "results": [
                        {
                            "id": "b1",
                            "type": "heading_1",
                            "heading_1": {"rich_text": [{"plain_text": "Q3 Goals"}]},
                            "has_children": False,
                        },
                        {
                            "id": "b2",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [{"plain_text": "Ship connectors and web ingest."}]
                            },
                            "has_children": False,
                        },
                    ],
                    "has_more": False,
                }
            )
        return _Resp({"results": [], "has_more": False})


def test_notion_list_changes(monkeypatch):
    monkeypatch.setattr("auralynq.connectors.notion.time.sleep", lambda *_: None)
    conn = NotionConnector("secret_tok")
    monkeypatch.setattr(conn, "_client", lambda: _FakeNotion())
    docs, cursor = conn.list_changes(None)
    assert len(docs) == 1
    d = docs[0]
    assert d.source == "notion://p1" and d.title == "Roadmap"
    assert "Q3 Goals" in d.text and "Ship connectors" in d.text
    assert d.authored_at == "2026-07-12T10:00:00.000Z"
    assert cursor == "2026-07-12T10:00:00.000Z"


def test_notion_not_configured():
    conn = NotionConnector("")
    assert conn.configured() is False
    assert "integration" in conn.setup_hint().lower()


# ── Slack ───────────────────────────────────────────────────────────────────


class _FakeSlack:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, path, params=None):
        if path == "/conversations.list":
            return _Resp(
                {
                    "ok": True,
                    "channels": [{"id": "C1", "name": "eng"}],
                    "response_metadata": {"next_cursor": ""},
                }
            )
        if path == "/conversations.history":
            return _Resp(
                {
                    "ok": True,
                    "messages": [
                        {"ts": "200.0", "text": "second"},
                        {"ts": "100.0", "text": "first"},
                    ],
                }
            )
        return _Resp({"ok": False, "error": "unknown_method"})


def test_slack_list_changes(monkeypatch):
    conn = SlackConnector("xoxb-test", rate_delay=0)
    monkeypatch.setattr(conn, "_client", lambda: _FakeSlack())
    docs, cursor = conn.list_changes(None)
    assert len(docs) == 1
    d = docs[0]
    assert d.source == "slack://C1" and d.title == "#eng"
    assert d.text == "first\nsecond"  # presented oldest→newest
    assert json.loads(cursor)["C1"] == "200.0"


def test_slack_not_configured():
    assert SlackConnector("").configured() is False


# ── Google Drive ────────────────────────────────────────────────────────────


class _FakeDriveService:
    def files(self):
        return self

    def changes(self):
        return self

    def list(self, **kw):
        self._op = ("list", kw)
        return self

    def getStartPageToken(self):
        self._op = ("token", {})
        return self

    def export(self, **kw):
        self._op = ("export", kw)
        return self

    def execute(self):
        op, _ = self._op
        if op == "list":
            return {
                "files": [
                    {
                        "id": "f1",
                        "name": "Spec.gdoc",
                        "mimeType": "application/vnd.google-apps.document",
                        "modifiedTime": "2026-07-12T09:00:00Z",
                        "webViewLink": "https://docs.google.com/f1",
                    }
                ]
            }
        if op == "token":
            return {"startPageToken": "tok-1"}
        if op == "export":
            return b"Rate limit is 3 rps per the API spec."
        return {}


def test_gdrive_full_backfill(monkeypatch):
    monkeypatch.setattr("auralynq.connectors.gdrive._sdk_available", lambda: True)
    conn = GDriveConnector('{"type":"service_account"}')
    monkeypatch.setattr(conn, "_service", lambda: _FakeDriveService())
    assert conn.configured() is True
    docs, cursor = conn.list_changes(None)
    assert len(docs) == 1
    assert docs[0].source == "gdrive://f1" and "Rate limit" in docs[0].text
    assert cursor == "tok-1"


def test_gdrive_needs_sdk_or_creds():
    # No creds → not configured; hint points at service account.
    conn = GDriveConnector("")
    assert conn.configured() is False


# ── Sync engine end-to-end ──────────────────────────────────────────────────


class _FakeConnector:
    name = "fake"

    def __init__(self, docs, cursor="cur-1"):
        self._docs = docs
        self._cursor = cursor

    def configured(self):
        return True

    def setup_hint(self):
        return "n/a"

    def list_changes(self, cursor):
        return self._docs, self._cursor

    def list_ids(self):
        return None


def _doc(source, text, h):
    return ConnectorDoc(
        id=source,
        source=source,
        title=source,
        text=text,
        content_hash=h,
        authored_at="2026-07-12T00:00:00Z",
    )


def test_sync_connector_indexes_and_is_incremental(monkeypatch):
    from auralynq.vectorstore.factory import get_store

    docs = [
        _doc("notion://a", "Ericsson holds FRAND patents on 5G standards. " * 4, "h-a"),
        _doc("notion://b", "Ford partners with AutoHarvest on open innovation. " * 4, "h-b"),
    ]
    conn = _FakeConnector(docs)

    r1 = sync_connector(conn)
    assert r1["configured"] is True
    assert r1["added"] == 2 and r1["updated"] == 0
    store = get_store()
    srcs = {c.source for c in store.all_chunks()}
    assert {"notion://a", "notion://b"} <= srcs

    # cursor persisted
    assert load_state()["fake"]["cursor"] == "cur-1"

    # same hashes → all unchanged, nothing re-indexed
    r2 = sync_connector(conn)
    assert r2["added"] == 0 and r2["updated"] == 0 and r2["unchanged"] == 2

    # a changed hash → updated
    conn._docs = [_doc("notion://a", "Ericsson now says the rate is 3 rps, not 5. " * 4, "h-a2")]
    r3 = sync_connector(conn)
    assert r3["updated"] == 1


def test_sync_unconfigured_reports_cleanly():
    class _Off(_FakeConnector):
        def configured(self):
            return False

    r = sync_connector(_Off([]))
    assert r["configured"] is False and r["errors"]
