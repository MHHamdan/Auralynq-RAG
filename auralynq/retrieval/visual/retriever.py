"""Late-interaction visual retriever.

Embeds the query into token vectors, MaxSim-ranks pages in the multi-vector
store, and returns the chunks on the winning pages — each annotated with the
patch's ``normalized_bbox`` so the answer region is localized on the page (feeds
straight into ``grounding/resolver``'s visual evidence).
"""

from __future__ import annotations

from typing import Any

from auralynq.ingest.models import Chunk
from auralynq.retrieval.base import Retriever
from auralynq.retrieval.models import Filter, RetrievalResult, ScoredChunk
from auralynq.retrieval.visual.embedder import PatchEmbedder, get_visual_embedder
from auralynq.retrieval.visual.store import MultiVectorStore


def _index_chunks(chunks: list[Chunk]) -> dict[tuple[str, int], list[Chunk]]:
    by_page: dict[tuple[str, int], list[Chunk]] = {}
    for c in chunks:
        if c.span.page is not None:
            by_page.setdefault((c.doc_id, c.span.page), []).append(c)
    return by_page


class VisualRetriever(Retriever):
    name = "visual"

    def __init__(
        self,
        store: MultiVectorStore | None = None,
        embedder: PatchEmbedder | None = None,
        chunks: list[Chunk] | None = None,
        settings: Any | None = None,
    ) -> None:
        from auralynq.config.settings import get_settings

        self.settings = settings or get_settings()
        self.store = (
            store if store is not None else MultiVectorStore.load(self.settings.visual_index_dir)
        )
        self.embedder = embedder or get_visual_embedder(self.settings)
        if chunks is None:
            chunks = self._load_chunks()
        self._by_page = _index_chunks(chunks)

    @staticmethod
    def _load_chunks() -> list[Chunk]:
        try:
            from auralynq.vectorstore.factory import get_store

            return get_store().all_chunks()
        except Exception:  # pragma: no cover - store unavailable
            return []

    def retrieve(self, query: str, k: int, filt: Filter | None = None) -> RetrievalResult:
        t0 = self._timer()
        qv = self.embedder.embed_query(query)
        n_tokens = max(qv.shape[0], 1) if qv.ndim == 2 else 1
        rerank_k = max(self.settings.visual.visual_rerank_k, k)
        hits = self.store.search(qv, k=rerank_k)
        scored: list[ScoredChunk] = []
        for h in hits:
            page_chunks = self._by_page.get((h.doc_id, h.page), [])
            if not page_chunks:
                continue
            chunk = page_chunks[0].model_copy(deep=True)
            chunk.metadata = {
                **chunk.metadata,
                "visual_grounding": {
                    "support_type": "visual",
                    "page": h.page,
                    "normalized_bbox": h.normalized_bbox(),
                    "patch_index": h.patch_index,
                },
            }
            # Map MaxSim (sum of per-token cosines) to a 0-1 score.
            score = max(0.0, min(1.0, (h.score / n_tokens + 1.0) / 2.0))
            scored.append(ScoredChunk(chunk=chunk, score=score, method="visual", rank=len(scored)))
            if len(scored) >= k:
                break
        took_ms = (self._timer() - t0) * 1000
        return RetrievalResult(
            query=query,
            method="visual",
            chunks=scored,
            took_ms=took_ms,
            metadata={"pages_scored": len(hits), "embedder": self.embedder.name},
        )
