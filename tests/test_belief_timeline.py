"""Bi-temporal belief timeline (Feature 04) — offline tests."""

from __future__ import annotations

from auralynq.beliefs import get_belief_store
from auralynq.beliefs.extractor import populate_beliefs
from auralynq.beliefs.store import BeliefStore
from auralynq.ingest.models import Chunk, SourceType
from auralynq.retrieval.pathrag.graph import KnowledgeGraph, Provenance
from auralynq.serving.app import create_app
from fastapi.testclient import TestClient


def _chunk(cid: str, source: str, authored: str) -> Chunk:
    return Chunk(
        id=cid,
        doc_id=f"doc_{cid}",
        ordinal=0,
        source=source,
        source_type=SourceType.text,
        text=f"{source} content",
        metadata={"authored_at": authored},
    )


def _kg(edges: list[tuple[str, str, str, str]]) -> KnowledgeGraph:
    """edges = [(src, relation, dst, chunk_id)]."""
    kg = KnowledgeGraph()
    for src, rel, dst, cid in edges:
        kg.add_entity(src, chunk_id=cid)
        kg.add_entity(dst, chunk_id=cid)
        kg.add_relation(src, dst, rel, Provenance(chunk_id=cid, source=f"{cid}.pdf"))
    return kg


def test_functional_relation_records_claim(tmp_path):
    store = BeliefStore(tmp_path / "b.db")
    kg = _kg([("Acme", "ceo", "Alice", "c0")])
    chunks = [_chunk("c0", "2020.pdf", "2020-01-01T00:00:00+00:00")]
    assert populate_beliefs(kg, chunks, store) == 1
    current = store.current("Acme")
    assert [c.object for c in current] == ["Alice"]
    assert current[0].valid_from == "2020-01-01T00:00:00+00:00"


def test_functional_relation_revision_supersedes(tmp_path):
    store = BeliefStore(tmp_path / "b.db")
    populate_beliefs(
        _kg([("Acme", "ceo", "Alice", "c0")]),
        [_chunk("c0", "2020.pdf", "2020-01-01T00:00:00+00:00")],
        store,
    )
    # A later ingest changes the CEO → revision.
    populate_beliefs(
        _kg([("Acme", "ceo", "Bob", "c1")]),
        [_chunk("c1", "2021.pdf", "2021-06-01T00:00:00+00:00")],
        store,
    )
    hist = store.history("Acme")
    assert [c.object for c in hist] == ["Alice", "Bob"]
    alice = hist[0]
    assert alice.valid_to == "2021-06-01T00:00:00+00:00"  # closed at the new fact's valid-time
    assert alice.superseded_by is not None
    assert [c.object for c in store.current("Acme")] == ["Bob"]
    # Valid-time travel: Alice was CEO in early 2021, Bob by 2022.
    assert [c.object for c in store.as_of("Acme", "2020-06-01T00:00:00+00:00")] == ["Alice"]
    assert [c.object for c in store.as_of("Acme", "2022-01-01T00:00:00+00:00")] == ["Bob"]


def test_multivalued_relation_accumulates(tmp_path):
    store = BeliefStore(tmp_path / "b.db")
    kg = _kg([("Acme", "partner", "X", "c0"), ("Acme", "partner", "Y", "c0")])
    chunks = [_chunk("c0", "2020.pdf", "2020-01-01T00:00:00+00:00")]
    populate_beliefs(kg, chunks, store)
    current = {c.object for c in store.current("Acme")}
    assert current == {"X", "Y"}  # neither supersedes the other


def test_timeline_endpoint():
    store = get_belief_store()  # default settings path (conftest temp data dir)
    populate_beliefs(
        _kg([("Globex", "hq", "Paris", "c0")]),
        [_chunk("c0", "2019.pdf", "2019-01-01T00:00:00+00:00")],
        store,
    )
    client = TestClient(create_app())
    r = client.get("/beliefs/Globex/timeline")
    assert r.status_code == 200
    body = r.json()
    assert body["entity"] == "Globex"
    assert body["current_count"] == 1
    claim = body["claims"][0]
    assert claim["predicate"] == "hq" and claim["object"] == "Paris"
    assert claim["current"] is True
