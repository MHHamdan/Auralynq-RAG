"""ColPali-style late-interaction visual retrieval.

Instead of collapsing a page to one embedding, ColPali (Faysse et al., 2024)
keeps a vector per image *patch* and scores a query by MaxSim — the sum, over
query tokens, of the best-matching patch. That patch also *localizes* the answer
region on the page, which plugs straight into Auralynq's visual grounding.

We reuse the page images already rendered for grounding
(``page_cache_dir/<doc_id>/page_XXXX.png``). The heavy GPU embedder lives behind
the optional ``colpali`` extra; a deterministic hash patch-embedder keeps the
whole path functional and offline ($0) when it is not installed.
"""

from auralynq.retrieval.visual.embedder import (
    HashPatchEmbedder,
    PatchEmbedder,
    get_visual_embedder,
)
from auralynq.retrieval.visual.indexer import build_visual_index
from auralynq.retrieval.visual.retriever import VisualRetriever
from auralynq.retrieval.visual.store import MultiVectorStore

__all__ = [
    "HashPatchEmbedder",
    "MultiVectorStore",
    "PatchEmbedder",
    "VisualRetriever",
    "build_visual_index",
    "get_visual_embedder",
]
