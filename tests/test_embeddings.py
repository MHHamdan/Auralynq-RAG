from __future__ import annotations

import numpy as np
from auralynq.embeddings import HashingEmbedder, get_embedder, resolved_provider


def test_hashing_embedder_is_deterministic():
    e1 = HashingEmbedder(dim=128)
    e2 = HashingEmbedder(dim=128)
    a = e1.embed(["flow based pruning"]).dense
    b = e2.embed(["flow based pruning"]).dense
    assert np.allclose(a, b)


def test_embedding_similarity_ranks_overlap_higher(sample_texts):
    emb = HashingEmbedder(dim=256)
    batch = emb.embed(sample_texts)
    q = emb.embed_query("flow based pruning of graph paths")
    sims = [emb.cosine(q.dense, batch.dense[i]) for i in range(len(sample_texts))]
    # The flow-pruning sentences should outrank the Paris sentence.
    assert sims[1] > sims[2]
    assert sims[0] > sims[2]


def test_sparse_vectors_present(sample_texts):
    emb = HashingEmbedder(dim=64)
    batch = emb.embed(sample_texts)
    assert len(batch.sparse) == len(sample_texts)
    assert all(isinstance(sp, dict) and sp for sp in batch.sparse)


def test_factory_resolves_hash_in_test_env():
    assert resolved_provider() == "hash"
    assert get_embedder().name == "hash"


def test_openai_embedder_dense_plus_derived_sparse(monkeypatch):
    """OpenAIEmbedder returns API dense vectors + a derived lexical sparse vector,
    so hybrid retrieval still works. The OpenAI client is stubbed (offline)."""
    import sys
    import types

    import numpy as np

    # Stub the `openai` SDK with a fake client returning deterministic vectors.
    fake = types.ModuleType("openai")

    class _Emb:
        def create(self, model, input):
            data = []
            for t in input:
                # 4-dim vector derived from text length so it's deterministic
                v = [float(len(t) % 7), 1.0, 0.5, 0.25]
                data.append(types.SimpleNamespace(embedding=v))
            return types.SimpleNamespace(data=data)

    class _Client:
        def __init__(self, api_key):
            self.embeddings = _Emb()

    fake.OpenAI = _Client
    monkeypatch.setitem(sys.modules, "openai", fake)

    from auralynq.embeddings.openai_embed import OpenAIEmbedder

    emb = OpenAIEmbedder(api_key="test", model="text-embedding-3-small")
    batch = emb.embed(["flow based pruning", "the cat sat"])
    assert batch.dense.shape == (2, 4)
    assert isinstance(batch.dense, np.ndarray)
    # derived sparse present + non-empty (enables hybrid fusion)
    assert len(batch.sparse) == 2
    assert all(sp for sp in batch.sparse)
    # query path works
    q = emb.embed_query("flow based pruning")
    assert q.dense.shape == (4,)
    assert q.sparse
