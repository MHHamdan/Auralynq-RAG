"""Visual Q&A: answer a question over retrieved document *page images*.

Pipeline: late-interaction visual retrieval picks the winning pages → we resolve
their cached PNGs (``page_cache_dir/<doc_id>/page_XXXX.png``) → a hosted VLM reads
the pages and answers with (Page N) citations. Deduplicates pages, caps how many
images are sent (``vlm_max_pages``), and degrades to a structured "unavailable"
result when the VLM is off/air-gapped/tokenless — never raises for those.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class VisualPage:
    doc_id: str
    page: int
    source: str
    image_path: Path


@dataclass
class VisualAnswer:
    answer: str
    pages: list[VisualPage] = field(default_factory=list)
    model: str = ""
    available: bool = True
    reason: str = ""


def _resolve_pages(chunks, settings, max_pages: int) -> list[VisualPage]:
    """Map retrieved chunks to on-disk page images, deduped, order preserved."""
    seen: set[tuple[str, int]] = set()
    pages: list[VisualPage] = []
    for sc in chunks:
        chunk = sc.chunk
        page = chunk.span.page
        if page is None:
            continue
        key = (chunk.doc_id, page)
        if key in seen:
            continue
        img = settings.page_cache_dir / chunk.doc_id / f"page_{page:04d}.png"
        if not img.exists():
            continue
        seen.add(key)
        pages.append(
            VisualPage(
                doc_id=chunk.doc_id,
                page=page,
                source=chunk.source or chunk.doc_id,
                image_path=img,
            )
        )
        if len(pages) >= max_pages:
            break
    return pages


def answer_visual_question(
    question: str,
    k: int = 6,
    *,
    settings: Any | None = None,
    retriever: Any | None = None,
    vlm: Any | None = None,
) -> VisualAnswer:
    """Retrieve the most relevant pages and have a VLM answer over their images.

    ``retriever`` / ``vlm`` are injectable for testing; by default they are built
    from settings (visual retriever + ``llm.vlm.get_vlm()``).
    """
    from auralynq.config.settings import get_settings

    s = settings or get_settings()

    if vlm is None:
        from auralynq.llm.vlm import get_vlm

        vlm = get_vlm()
    if vlm is None:
        return VisualAnswer(answer="", available=False, reason="vlm_unavailable")

    if retriever is None:
        from auralynq.retrieval.visual import VisualRetriever

        retriever = VisualRetriever(settings=s)
    res = retriever.retrieve(question, k)
    pages = _resolve_pages(res.chunks, s, s.visual.vlm_max_pages)
    if not pages:
        return VisualAnswer(
            answer="The provided pages do not contain enough information to answer this.",
            available=True,
            reason="no_pages",
            model=s.visual.vlm_model,
        )

    text = vlm.answer(
        question,
        [p.image_path for p in pages],
        max_tokens=s.visual.vlm_max_tokens,
    )
    return VisualAnswer(answer=text, pages=pages, model=s.visual.vlm_model)
