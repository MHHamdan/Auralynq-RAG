"""Contextual Retrieval — chunk-situating context prepended before embedding.

Offline: a fake LLM supplies deterministic contexts; asserts context is applied
to the embedded text but never to display/citation, and that it's gated off by
default and idempotent.
"""

from __future__ import annotations

from auralynq.config import get_settings, reload_settings
from auralynq.ingest.models import Chunk, Document, SourceType


class _FakeLLM:
    name = "fake"

    def __init__(self):
        self.calls = 0

    def generate(self, prompt, **kw):
        self.calls += 1
        return "This chunk is from the FRAND licensing section of the Ericsson report."


def _doc(n_chunks=3):
    chunks = [
        Chunk(id=Chunk.make_id("d1", i), doc_id="d1", text=f"Sentence number {i} about Ericsson patents.", ordinal=i, source="e.pdf", source_type=SourceType.html)
        for i in range(n_chunks)
    ]
    return Document(id="d1", source="e.pdf", source_type=SourceType.html, title="Ericsson", content_hash="h", chunks=chunks)


def test_embed_text_prepends_context_only_when_present():
    c = Chunk(id="x", doc_id="d", text="raw body")
    assert c.embed_text() == "raw body"
    c.context = "situating context"
    assert c.embed_text() == "situating context\n\nraw body"
    # display/citation text is untouched
    assert c.text == "raw body"


def test_contextual_disabled_by_default():
    reload_settings()
    assert get_settings().retrieval.contextual_enabled is False


def test_contextualize_sets_context_and_is_idempotent():
    from auralynq.ingest.contextualize import contextualize_document

    doc = _doc(3)
    llm = _FakeLLM()
    done = contextualize_document(doc, llm=llm)
    assert done == 3
    assert all(c.context for c in doc.chunks)
    assert all("FRAND licensing section" in c.context for c in doc.chunks)
    # embedded text carries context; raw text unchanged
    assert doc.chunks[0].embed_text().startswith("This chunk is from")
    assert doc.chunks[0].text == "Sentence number 0 about Ericsson patents."
    # idempotent: already-set contexts are not re-generated
    again = contextualize_document(doc, llm=llm)
    assert again == 0 and llm.calls == 3


def test_index_documents_contextualizes_when_enabled(monkeypatch):
    from auralynq.vectorstore.factory import get_store

    monkeypatch.setenv("AURALYNQ_RETRIEVAL__CONTEXTUAL_ENABLED", "true")
    reload_settings()
    get_store.cache_clear()
    llm = _FakeLLM()
    monkeypatch.setattr("auralynq.llm.factory.get_llm", lambda: llm)

    from auralynq.pipeline import index_documents

    doc = _doc(2)
    stats = index_documents([doc])
    assert stats["chunks_indexed"] == 2
    assert llm.calls == 2  # one per chunk
    # the in-memory chunks now carry context, but display text is unchanged
    assert all(c.context for c in doc.chunks)
    assert doc.chunks[0].text.startswith("Sentence number 0")

    # stored chunks keep the original display text (context is separate)
    stored = {c.id: c for c in get_store().all_chunks()}
    assert stored[doc.chunks[0].id].text == "Sentence number 0 about Ericsson patents."
