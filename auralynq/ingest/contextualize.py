"""Contextual Retrieval (Anthropic) — situate each chunk in its document.

At ingest, an LLM writes a short context that places a chunk within the whole
document ("This section of the Q3 report covers revenue growth…"). That context
is prepended to the chunk before embedding + sparse indexing, so retrieval keys
on document-level context that a bare chunk loses. Anthropic reports ~35% fewer
retrieval failures (embeddings) / 49% (+contextual BM25). The generated context
is stored on ``Chunk.context`` and never shown or cited — display/citation keep
the original text.

Off by default and gated in the pipeline: it costs one LLM call per chunk and
only helps with a real model (the extractive fallback just echoes text).
"""

from __future__ import annotations

from auralynq.config import get_settings
from auralynq.ingest.models import Document
from auralynq.telemetry import get_logger

_log = get_logger("auralynq.contextualize")

# Anthropic's situating-context prompt (adapted).
_PROMPT = (
    "<document>\n{doc}\n</document>\n\n"
    "Here is a chunk we want to situate within the whole document:\n"
    "<chunk>\n{chunk}\n</chunk>\n\n"
    "Give a short, succinct context (1-2 sentences) that situates this chunk "
    "within the overall document, to improve search retrieval of the chunk. "
    "Answer ONLY with the succinct context and nothing else."
)


def _reconstruct_doc_text(doc: Document, limit: int) -> str:
    """Approximate the document body from its chunks (ordinal order)."""
    parts = [c.text for c in sorted(doc.chunks, key=lambda c: c.ordinal)]
    return "\n".join(parts)[:limit]


def contextualize_document(doc: Document, *, llm=None, settings=None) -> int:
    """Set ``chunk.context`` for every chunk in ``doc``. Returns the count
    contextualized. Best-effort: a failed chunk keeps an empty context and still
    indexes on its raw text."""
    s = settings or get_settings()
    if not doc.chunks:
        return 0
    if llm is None:
        from auralynq.llm.factory import get_llm

        llm = get_llm()

    doc_text = _reconstruct_doc_text(doc, s.retrieval.contextual_max_doc_chars)
    cap = s.retrieval.contextual_max_context_chars
    done = 0
    for c in doc.chunks:
        if c.context:  # already contextualized (idempotent re-index)
            continue
        try:
            ctx = llm.generate(
                _PROMPT.format(doc=doc_text, chunk=c.text),
                max_tokens=80,
                temperature=0.0,
            ).strip()
        except Exception as exc:  # never let contextualization break ingest
            _log.warning("contextualize.failed", chunk=c.id, error=str(exc))
            ctx = ""
        if ctx:
            c.context = ctx[:cap]
            done += 1
    _log.info("contextualize.document", doc=doc.id, chunks=len(doc.chunks), contextualized=done)
    return done


def contextualize_documents(documents: list[Document], *, settings=None) -> int:
    s = settings or get_settings()
    from auralynq.llm.factory import get_llm

    llm = get_llm()
    return sum(contextualize_document(d, llm=llm, settings=s) for d in documents)
