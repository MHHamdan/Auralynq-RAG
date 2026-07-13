"""Build the multi-vector visual index from cached page images.

Reuses the PNGs already rendered for grounding
(``page_cache_dir/<doc_id>/page_XXXX.png``) — no re-rendering. Best-effort and
gated by the caller; a failure never blocks ingest.
"""

from __future__ import annotations

from typing import Any

from auralynq.retrieval.visual.embedder import PatchEmbedder, get_visual_embedder
from auralynq.retrieval.visual.store import MultiVectorStore
from auralynq.telemetry import get_logger

_log = get_logger("auralynq.visual.indexer")


def build_visual_index(settings: Any | None = None, embedder: PatchEmbedder | None = None) -> int:
    """Embed every cached page image into the multi-vector store. Returns pages indexed."""
    from auralynq.config.settings import get_settings

    s = settings or get_settings()
    cache_dir = s.page_cache_dir
    if not cache_dir.exists():
        return 0
    emb = embedder or get_visual_embedder(s)
    store = MultiVectorStore()
    n = 0
    for doc_dir in sorted(p for p in cache_dir.iterdir() if p.is_dir()):
        for png in sorted(doc_dir.glob("page_*.png")):
            try:
                page = int(png.stem.split("_")[1])
            except (IndexError, ValueError):
                continue
            try:
                patches, grid = emb.embed_image(png)
            except Exception as exc:  # pragma: no cover - decode/model hiccup
                _log.warning("visual.embed_failed", path=str(png), error=str(exc))
                continue
            store.add_page(doc_dir.name, page, patches, grid)
            n += 1
    store.save(s.visual_index_dir)
    _log.info("visual.index_built", pages=n, embedder=emb.name)
    return n
