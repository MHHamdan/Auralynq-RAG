"""GraphRAG community detection + summaries (Feature 02) — offline tests."""

from __future__ import annotations

from auralynq.config.settings import Settings
from auralynq.retrieval.graphrag import (
    build_communities,
    detect_communities,
    load_communities,
    save_communities,
)
from auralynq.retrieval.pathrag.graph import KnowledgeGraph, Provenance
from auralynq.serving.app import create_app
from fastapi.testclient import TestClient


def _two_cluster_kg() -> KnowledgeGraph:
    """Two dense triangles joined by a single weak edge → two communities."""
    kg = KnowledgeGraph()
    cluster_a = [("Paris", "France"), ("France", "Europe"), ("Paris", "Europe")]
    cluster_b = [("Python", "Django"), ("Django", "ORM"), ("Python", "ORM")]
    for src, dst in cluster_a:
        kg.add_entity(src, chunk_id="ca")
        kg.add_entity(dst, chunk_id="ca")
        kg.add_relation(src, dst, "related", Provenance(chunk_id="ca", source="geo.txt"))
    for src, dst in cluster_b:
        kg.add_entity(src, chunk_id="cb")
        kg.add_entity(dst, chunk_id="cb")
        kg.add_relation(src, dst, "uses", Provenance(chunk_id="cb", source="tech.txt"))
    # single bridge edge (weak) so the graph is connected but still two communities
    kg.add_relation("Europe", "Python", "mentions", Provenance(chunk_id="ca", source="geo.txt"))
    return kg


class _StubLLM:
    name = "stub"

    def generate(self, prompt, *, system=None, temperature=None, max_tokens=None) -> str:
        return "A theme summary of the community."


def test_detect_two_communities():
    comms = detect_communities(_two_cluster_kg(), min_size=3, algo="louvain")
    assert len(comms) == 2
    # Each community keeps its entities + internal relations.
    sizes = sorted(c.size for c in comms)
    assert sizes == [3, 3]
    assert all(c.relations for c in comms)


def test_min_size_gate_filters_small():
    kg = KnowledgeGraph()
    kg.add_entity("A", chunk_id="c")
    kg.add_entity("B", chunk_id="c")
    kg.add_relation("A", "B", "r", Provenance(chunk_id="c", source="s.txt"))
    assert detect_communities(kg, min_size=3) == []


def test_greedy_algo_also_detects():
    comms = detect_communities(_two_cluster_kg(), min_size=3, algo="greedy")
    assert len(comms) >= 1


def test_build_summarizes_and_persists(tmp_path):
    s = Settings(data_dir=tmp_path)
    s.graphrag.enabled = True
    comms = build_communities(_two_cluster_kg(), llm=_StubLLM(), settings=s)
    assert len(comms) == 2
    assert all(c.summary == "A theme summary of the community." for c in comms)
    # Persisted and reloadable.
    loaded = load_communities(s.communities_path)
    assert len(loaded) == 2
    assert loaded[0]["summary"]
    assert "geo.txt" in loaded[0]["sources"] or "tech.txt" in loaded[0]["sources"]


def test_save_load_roundtrip(tmp_path):
    comms = detect_communities(_two_cluster_kg(), min_size=3)
    path = tmp_path / "communities.json"
    save_communities(comms, path)
    loaded = load_communities(path)
    assert len(loaded) == 2
    assert load_communities(tmp_path / "missing.json") == []


def test_communities_endpoint(monkeypatch):
    monkeypatch.setenv("AURALYNQ_GRAPHRAG__ENABLED", "1")
    from auralynq.config import reload_settings

    reload_settings()
    from auralynq.config.settings import get_settings

    s = get_settings()
    build_communities(_two_cluster_kg(), llm=_StubLLM(), settings=s)
    client = TestClient(create_app())
    r = client.get("/graphrag/communities")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["count"] == 2
    assert body["communities"][0]["summary"]
