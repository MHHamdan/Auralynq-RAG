"""Proactive contradiction alerts (Feature 03) — offline tests."""

from __future__ import annotations

from auralynq.beliefs.alerts import Alert, AlertStore, get_alert_store
from auralynq.config.settings import Settings
from auralynq.ingest.models import Chunk, SourceType
from auralynq.retrieval.pathrag.builder import build_from_chunks
from auralynq.serving.app import create_app
from auralynq.wiki.generator import synthesize_wiki
from fastapi.testclient import TestClient


def _alert(entity="Paris", old="small", new="large") -> Alert:
    from auralynq.beliefs.alerts import _alert_id

    return Alert(id=_alert_id(entity, old, new), entity=entity, old_claim=old, new_claim=new)


# --------------------------------------------------------------- store ------
def test_emit_list_and_idempotency(tmp_path):
    s = AlertStore(tmp_path / "alerts.jsonl")
    assert s.emit([_alert()]) == 1
    assert s.emit([_alert()]) == 0  # same id → not re-appended
    assert len(s.list_alerts()) == 1
    assert s.unread_count() == 1


def test_emit_contradictions_maps_fields(tmp_path):
    s = AlertStore(tmp_path / "alerts.jsonl")
    n = s.emit_contradictions(
        [{"entity": "Acme", "old_claim": "profit", "new_claim": "loss", "why": "Q3"}],
        source="q3.pdf",
    )
    assert n == 1
    a = s.list_alerts()[0]
    assert a.entity == "Acme" and a.new_claim == "loss" and a.source == "q3.pdf"


def test_mark_read(tmp_path):
    s = AlertStore(tmp_path / "alerts.jsonl")
    s.emit([_alert("A", "x", "y"), _alert("B", "p", "q")])
    assert s.unread_count() == 2
    assert len(s.list_alerts(unread_only=True)) == 2
    assert s.mark_read([_alert("A", "x", "y").id]) == 1
    assert s.unread_count() == 1
    assert s.mark_read() == 1  # mark all remaining
    assert s.unread_count() == 0
    assert s.mark_read() == 0  # nothing left to change


# ------------------------------------------------------- generator hook -----
def _chunks() -> list[Chunk]:
    return [
        Chunk(
            id="c0",
            doc_id="d",
            ordinal=0,
            source="geo.txt",
            source_type=SourceType.text,
            text="Paris is the capital of France.",
        ),
    ]


class _DualStub:
    """Markdown for synthesis; a JSON contradiction for the detection prompt."""

    def generate(self, p, *, system=None, temperature=None, max_tokens=None):
        if system and "CONTRADICTIONS" in system:
            return '[{"old_claim":"Paris is small","new_claim":"Paris is large","why":"size"}]'
        return "Paris is a city [1]."


def test_sync_emits_alert_on_contradiction(tmp_path):
    s = Settings(data_dir=tmp_path)
    s.wiki.enabled = True
    s.wiki.min_mentions = 1
    llm = _DualStub()
    synthesize_wiki(build_from_chunks(_chunks()), _chunks(), llm=llm, settings=s)  # first page
    extra = [
        *_chunks(),
        Chunk(
            id="c9",
            doc_id="d2",
            ordinal=0,
            source="new.txt",
            source_type=SourceType.text,
            text="Paris is a major capital city in France.",
        ),
    ]
    synthesize_wiki(build_from_chunks(extra), extra, llm=llm, settings=s)  # new source → conflict

    store = get_alert_store(s.storage_dir / "alerts.jsonl")
    alerts = store.list_alerts(unread_only=True)
    assert len(alerts) >= 1
    assert "paris" in {a.entity.lower() for a in alerts}
    assert all("new.txt" in a.source for a in alerts)


# ---------------------------------------------------------- endpoints -------
def test_alerts_endpoints_roundtrip():
    # get_alert_store() defaults to settings.storage_dir/alerts.jsonl (conftest
    # temp data dir), which is what the endpoints read.
    store = get_alert_store()
    store.emit([_alert("Widget", "cheap", "expensive")])
    client = TestClient(create_app())

    r = client.get("/alerts")
    assert r.status_code == 200
    body = r.json()
    assert body["unread_count"] == 1
    assert body["alerts"][0]["entity"] == "Widget"
    aid = body["alerts"][0]["id"]

    r2 = client.post("/alerts/read", json={"ids": [aid]})
    assert r2.status_code == 200 and r2.json()["marked"] == 1
    assert client.get("/alerts").json()["unread_count"] == 0
