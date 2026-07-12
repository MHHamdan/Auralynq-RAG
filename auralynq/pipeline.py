"""End-to-end indexing pipeline: corpus → vector index + knowledge graph.

Ties together ingestion, embeddings, the vector store and the PathRAG knowledge
graph. Persists both indexes so retrieval/agent can run in a fresh process.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from auralynq.config import get_settings
from auralynq.embeddings.factory import get_embedder
from auralynq.ingest.chunking import chunk_text
from auralynq.ingest.models import Chunk, Document, SourceSpan, SourceType
from auralynq.ingest.pipeline import _Manifest, ingest_path
from auralynq.retrieval.pathrag.builder import build_from_chunks
from auralynq.retrieval.pathrag.graph import KnowledgeGraph
from auralynq.telemetry import get_logger
from auralynq.utils import chunked, stable_id
from auralynq.vectorstore.factory import get_store
from auralynq.vectorstore.memory_store import MemoryStore

_log = get_logger("auralynq.pipeline")


def graph_path() -> Path:
    return get_settings().index_dir / "graph.json"


def index_documents(documents: list[Document]) -> dict[str, Any]:
    """Embed + upsert a set of documents, then rebuild the KG + Compounding Wiki
    from the *full* stored set. Shared by directory ingest (:func:`build_index`)
    and single-source ingest (:func:`ingest_web_page`, connectors)."""
    s = get_settings()
    s.ensure_dirs()
    store = get_store()
    embedder = get_embedder()

    # Contextual Retrieval (Anthropic): situate each chunk in its document before
    # embedding + sparse indexing. Gated + non-fatal; never blocks indexing.
    if s.retrieval.contextual_enabled and documents:
        try:
            from auralynq.ingest.contextualize import contextualize_documents

            contextualize_documents(documents, settings=s)
        except Exception as e:  # pragma: no cover - non-fatal by design
            _log.warning("contextualize.skipped", error=str(e))

    all_chunks: list[Chunk] = [c for d in documents for c in d.chunks]
    n_indexed = 0
    for batch in chunked(all_chunks, s.embedding.batch_size):
        # embed_text() prepends the situating context when present, else raw text.
        emb = embedder.embed([c.embed_text() for c in batch])
        n_indexed += store.upsert(batch, emb)

    if isinstance(store, MemoryStore):
        store.save()

    # Rebuild the knowledge graph from the *full* indexed set (not just newly
    # ingested chunks) so an idempotent re-index never wipes the graph. Falls
    # back to this run's chunks if the store can't enumerate (e.g. remote Qdrant).
    kg_chunks = store.all_chunks() or all_chunks
    wiki_pages = 0
    if kg_chunks:
        kg = build_from_chunks(kg_chunks)
        kg.save(graph_path())
        # Compounding Wiki — synthesize durable entity pages from the fresh KG.
        # Additive and gated; never blocks indexing on failure.
        if s.wiki.enabled and s.wiki.auto_synthesize:
            try:
                from auralynq.wiki.generator import synthesize_wiki

                wiki_pages = synthesize_wiki(kg, kg_chunks, settings=s)
            except Exception as e:  # pragma: no cover - non-fatal by design
                _log.warning("wiki.synthesis_failed", error=str(e))
    else:
        kg = load_graph()  # nothing to index and nothing stored; keep existing

    if documents:
        _write_last_ingested(s.index_dir, documents)
        _write_doc_meta(s.storage_dir, documents)

    stats: dict[str, Any] = {
        "backend": store.backend,
        "embedder": embedder.name,
        "chunks_indexed": n_indexed,
        "store_count": store.count(),
        "entities": kg.n_entities,
        "relations": kg.n_relations,
    }
    if s.wiki.enabled:
        stats["wiki_pages"] = wiki_pages
    return stats


def build_index(input_dir: Path, rebuild: bool = False) -> dict[str, Any]:
    s = get_settings()
    s.ensure_dirs()
    store = get_store()

    if rebuild:
        store.clear()

    # Force a full ingest when the store is empty (e.g. the index dir was cleared
    # but the ingest manifest persisted) so the index is never left empty due to
    # a stale idempotency manifest.
    force = rebuild or store.count() == 0
    result = ingest_path(Path(input_dir), recursive=True, force=force)

    stats = index_documents(result.documents)
    stats["documents"] = result.n_documents
    stats["skipped"] = result.n_skipped
    _log.info("index.built", **stats)
    return stats


def ingest_web_page(url: str, *, force: bool = False) -> dict[str, Any]:
    """Fetch, extract and index a single web page, preserving provenance
    (final URL, title, byline, fetch time) and a content hash for re-crawl.

    Idempotent per URL via the shared ingest manifest: an unchanged page is
    skipped unless ``force``. The chunk ``source`` is the final URL, so citations
    resolve straight back to the page.
    """
    from auralynq.ingest.web import fetch_url

    s = get_settings()
    s.ensure_dirs()
    page = fetch_url(
        url,
        timeout=s.web.timeout_s,
        max_bytes=s.web.max_bytes,
        allow_private=s.web.allow_private_hosts,
    )

    manifest = _Manifest(s.storage_dir / "ingest_manifest.json")
    if not force and manifest.unchanged(page.url, page.content_hash):
        return {
            "documents": 0,
            "skipped": 1,
            "chunks_indexed": 0,
            "url": page.url,
            "title": page.title,
            "unchanged": True,
        }

    doc_id = stable_id(page.url)
    prov = page.provenance()
    chunks: list[Chunk] = []
    for ordinal, tc in enumerate(chunk_text(page.text)):
        chunks.append(
            Chunk(
                id=Chunk.make_id(doc_id, ordinal),
                doc_id=doc_id,
                text=tc.text,
                ordinal=ordinal,
                span=SourceSpan(start_char=tc.start_char, end_char=tc.end_char, section=tc.section),
                title=page.title,
                source=page.url,
                source_type=SourceType.html,
                # `connector` + `authored_at` power cross-source contradiction flags.
                metadata={"web": prov, "connector": "web", "authored_at": page.fetched_at},
            )
        )
    doc = Document(
        id=doc_id,
        source=page.url,
        source_type=SourceType.html,
        title=page.title,
        content_hash=page.content_hash,
        metadata={"web": prov, "connector": "web"},
        chunks=chunks,
    )

    stats = index_documents([doc])
    manifest.update(page.url, page.content_hash)
    manifest.save()
    stats.update({"documents": 1, "skipped": 0, "url": page.url, "title": page.title})
    _log.info("web.indexed", url=page.url, chunks=len(chunks))
    return stats


def _write_last_ingested(index_dir: Path, docs: list[Document]) -> None:
    """Write last_ingested.json: the document with the newest source mtime."""
    import datetime as _dt

    newest_doc = docs[-1]  # default: last in ingestion order
    newest_mtime = 0.0
    for d in docs:
        try:
            mtime = Path(d.source).stat().st_mtime
            if mtime > newest_mtime:
                newest_mtime = mtime
                newest_doc = d
        except OSError:
            pass
    name = newest_doc.title or Path(newest_doc.source).name
    ts = (
        _dt.datetime.fromtimestamp(newest_mtime, tz=_dt.UTC).isoformat()
        if newest_mtime > 0
        else _dt.datetime.now(tz=_dt.UTC).isoformat()
    )
    try:
        sidecar = index_dir / "last_ingested.json"
        sidecar.write_text(
            json.dumps({"name": name, "source": newest_doc.source, "ingested_at": ts}),
            encoding="utf-8",
        )
    except Exception:
        pass


def _write_doc_meta(storage_dir: Path, docs: list[Document]) -> None:
    """Write/merge doc_meta.json — consumed by visual grounding endpoints."""
    import contextlib

    meta_path = storage_dir / "doc_meta.json"
    existing: dict[str, dict] = {}
    if meta_path.exists():
        with contextlib.suppress(Exception):
            existing = json.loads(meta_path.read_text(encoding="utf-8"))
    for doc in docs:
        existing[doc.id] = {
            "title": doc.title or Path(doc.source).name,
            "source": doc.source,
            "source_type": doc.source_type.value,
            "page_dimensions": doc.page_dimensions,
            "visual_grounding_version": doc.visual_grounding_version,
            "n_pages": len(doc.page_dimensions),
            "n_chunks": doc.n_chunks,
            "n_chunks_with_bbox": sum(
                1 for c in doc.chunks if (c.metadata.get("visual_grounding") or {}).get("has_bbox")
            ),
        }
    with contextlib.suppress(Exception):
        meta_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def load_graph() -> KnowledgeGraph:
    p = graph_path()
    if p.exists():
        return KnowledgeGraph.load(p)
    return KnowledgeGraph()
