"""End-to-end indexing pipeline: corpus → vector index + knowledge graph.

Ties together ingestion, embeddings, the vector store and the PathRAG knowledge
graph. Persists both indexes so retrieval/agent can run in a fresh process.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from auralynq.config import get_settings
from auralynq.embeddings.factory import get_embedder
from auralynq.ingest.models import Chunk
from auralynq.ingest.pipeline import ingest_path
from auralynq.retrieval.pathrag.builder import build_from_chunks
from auralynq.retrieval.pathrag.graph import KnowledgeGraph
from auralynq.telemetry import get_logger
from auralynq.utils import chunked
from auralynq.vectorstore.factory import get_store
from auralynq.vectorstore.memory_store import MemoryStore

_log = get_logger("auralynq.pipeline")


def graph_path() -> Path:
    return get_settings().index_dir / "graph.json"


def build_index(input_dir: Path, rebuild: bool = False) -> dict[str, Any]:
    s = get_settings()
    s.ensure_dirs()
    store = get_store()
    embedder = get_embedder()

    if rebuild:
        store.clear()

    # Force a full ingest when the store is empty (e.g. the index dir was cleared
    # but the ingest manifest persisted) so the index is never left empty due to
    # a stale idempotency manifest.
    force = rebuild or store.count() == 0
    result = ingest_path(Path(input_dir), recursive=True, force=force)
    all_chunks: list[Chunk] = [c for d in result.documents for c in d.chunks]

    n_indexed = 0
    for batch in chunked(all_chunks, s.embedding.batch_size):
        emb = embedder.embed([c.text for c in batch])
        n_indexed += store.upsert(batch, emb)

    if isinstance(store, MemoryStore):
        store.save()

    # Rebuild the knowledge graph from the *full* indexed set (not just newly
    # ingested chunks) so an idempotent re-index never wipes the graph. Falls
    # back to this run's chunks if the store can't enumerate (e.g. remote Qdrant).
    kg_chunks = store.all_chunks() or all_chunks
    if kg_chunks:
        kg = build_from_chunks(kg_chunks)
        kg.save(graph_path())
    else:
        kg = load_graph()  # nothing to index and nothing stored; keep existing

    stats = {
        "backend": store.backend,
        "embedder": embedder.name,
        "documents": result.n_documents,
        "skipped": result.n_skipped,
        "chunks_indexed": n_indexed,
        "store_count": store.count(),
        "entities": kg.n_entities,
        "relations": kg.n_relations,
    }
    _log.info("index.built", **stats)
    return stats


def load_graph() -> KnowledgeGraph:
    p = graph_path()
    if p.exists():
        return KnowledgeGraph.load(p)
    return KnowledgeGraph()
