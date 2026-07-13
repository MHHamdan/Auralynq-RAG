"""ColPali late-interaction visual retrieval (Feature 01) — offline tests.

The GPU ColPali model is exercised only behind an importorskip; the numpy
MaxSim store, hash patch-embedder, indexer, retriever and endpoint all run at $0.
"""

from __future__ import annotations

import numpy as np
import pytest
from auralynq.config import reload_settings
from auralynq.config.settings import Settings
from auralynq.ingest.models import Chunk, SourceSpan, SourceType
from auralynq.retrieval.visual import (
    HashPatchEmbedder,
    MultiVectorStore,
    VisualRetriever,
    build_visual_index,
)
from auralynq.serving.app import create_app
from fastapi.testclient import TestClient


# ------------------------------------------------------- MultiVectorStore ----
def test_maxsim_ranks_and_localizes():
    store = MultiVectorStore()
    store.add_page("docA", 1, np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=np.float32), (1, 2))
    store.add_page("docB", 1, np.array([[0, 0, 1, 0], [0, 0, 0, 1]], dtype=np.float32), (1, 2))
    hits = store.search(np.array([[1, 0, 0, 0]], dtype=np.float32), k=2)
    assert hits[0].doc_id == "docA"
    assert hits[0].score > hits[1].score
    bbox = hits[0].normalized_bbox()
    assert len(bbox) == 4 and all(0.0 <= x <= 1.0 for x in bbox)
    assert bbox == [0.0, 0.0, 0.5, 1.0]  # patch 0 of a 1x2 grid


def test_store_save_load_roundtrip(tmp_path):
    store = MultiVectorStore()
    store.add_page("doc1", 1, np.array([[1, 0], [0, 1]], dtype=np.float32), (2, 1))
    store.save(tmp_path / "visual")
    loaded = MultiVectorStore.load(tmp_path / "visual")
    assert len(loaded) == 1
    assert loaded.search(np.array([[1, 0]], dtype=np.float32), k=1)[0].doc_id == "doc1"
    assert len(MultiVectorStore.load(tmp_path / "missing")) == 0


# --------------------------------------------------------- HashPatchEmbedder -
def _png(path, color=(120, 120, 120), size=(32, 32)):
    from PIL import Image

    Image.new("RGB", size, color).save(path)


def test_hash_embedder_shapes_and_determinism(tmp_path):
    p = tmp_path / "page_0001.png"
    _png(p)
    emb = HashPatchEmbedder(grid=8)
    patches, grid = emb.embed_image(p)
    assert patches.shape == (64, emb.dim) and grid == (8, 8)
    assert np.allclose(np.linalg.norm(patches, axis=1), 1.0, atol=1e-5)
    patches2, _ = emb.embed_image(p)
    assert np.array_equal(patches, patches2)  # deterministic
    q = emb.embed_query("hello world")
    assert q.ndim == 2 and q.shape[1] == emb.dim


# ---------------------------------------------------------------- indexer ----
def test_build_visual_index(tmp_path):
    s = Settings(data_dir=tmp_path)
    doc_dir = s.page_cache_dir / "doc1"
    doc_dir.mkdir(parents=True)
    _png(doc_dir / "page_0001.png")
    _png(doc_dir / "page_0002.png")
    n = build_visual_index(settings=s)
    assert n == 2
    loaded = MultiVectorStore.load(s.visual_index_dir)
    assert len(loaded) == 2


# --------------------------------------------------------------- retriever ---
class _StubEmb:
    name = "stub"

    def embed_image(self, path, grid=None):
        return np.array([[1, 0, 0, 0]], dtype=np.float32), (1, 1)

    def embed_query(self, text):
        return np.array([[1, 0, 0, 0]], dtype=np.float32)


def test_visual_retriever_attaches_bbox(tmp_path):
    s = Settings(data_dir=tmp_path)
    store = MultiVectorStore()
    store.add_page("doc1", 1, np.array([[1, 0, 0, 0]], dtype=np.float32), (1, 1))
    chunk = Chunk(
        id="c0",
        doc_id="doc1",
        text="the page text",
        source="d.pdf",
        source_type=SourceType.pdf,
        span=SourceSpan(page=1),
    )
    r = VisualRetriever(store=store, embedder=_StubEmb(), chunks=[chunk], settings=s)
    res = r.retrieve("where is the total", k=3)
    assert res.method == "visual" and res.chunks
    vg = res.chunks[0].chunk.metadata["visual_grounding"]
    assert vg["support_type"] == "visual" and vg["page"] == 1
    assert len(vg["normalized_bbox"]) == 4
    assert 0.0 <= res.chunks[0].score <= 1.0


# --------------------------------------------------------------- endpoint ----
def test_visual_search_disabled_by_default():
    client = TestClient(create_app())
    body = client.get("/visual/search", params={"q": "invoice total"}).json()
    assert body["enabled"] is False


def test_visual_search_enabled(monkeypatch):
    monkeypatch.setenv("AURALYNQ_VISUAL__VISUAL_RETRIEVAL_ENABLED", "1")
    reload_settings()
    client = TestClient(create_app())
    r = client.get("/visual/search", params={"q": "invoice total"})
    assert r.status_code == 200
    assert r.json()["enabled"] is True  # empty hits ok with no index


# ------------------------------------------------------- ColPali (GPU) -------
@pytest.mark.integration
def test_colpali_embedder_importable():
    pytest.importorskip("colpali_engine", reason="colpali extra not installed")
    from auralynq.retrieval.visual.colpali_embedder import ColPaliEmbedder

    assert ColPaliEmbedder.name == "colpali"
