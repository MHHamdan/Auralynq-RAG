"""Hosted VLM page-image Q&A (HF Inference Providers).

Offline: we assert the safety guards (disabled/air-gapped/tokenless → None),
the multimodal message construction (data URIs, page labels), and the retrieval
→ page-image → VLM orchestration with injected fakes. No network calls.
"""

from __future__ import annotations

import base64

from auralynq.config import get_settings, reload_settings
from auralynq.ingest.models import Chunk, SourceSpan, SourceType
from auralynq.llm.vlm import HuggingFaceVLM, encode_image, get_vlm
from auralynq.retrieval.models import RetrievalResult, ScoredChunk
from auralynq.retrieval.visual.vlm_qa import answer_visual_question


def _png(path):
    # 1x1 PNG (smallest valid) so encode_image has real bytes to read.
    data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42m"
        "NkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    )
    path.write_bytes(data)


# ------------------------------------------------------------- get_vlm guards


def test_vlm_disabled_returns_none(monkeypatch):
    monkeypatch.setenv("AURALYNQ_VISUAL__VLM_ENABLED", "false")
    reload_settings()
    assert get_vlm() is None


def test_vlm_tokenless_returns_none(monkeypatch):
    monkeypatch.setenv("AURALYNQ_VISUAL__VLM_ENABLED", "true")
    monkeypatch.setenv("HUGGINGFACE_TOKEN", "")
    reload_settings()
    assert get_vlm() is None


def test_vlm_air_gapped_returns_none(monkeypatch):
    monkeypatch.setenv("AURALYNQ_VISUAL__VLM_ENABLED", "true")
    monkeypatch.setenv("HUGGINGFACE_TOKEN", "hf_dummy_test_token")
    monkeypatch.setenv("AURALYNQ_AIR_GAPPED", "true")
    reload_settings()
    assert get_vlm() is None


def test_vlm_enabled_with_token_builds(monkeypatch):
    monkeypatch.setenv("AURALYNQ_VISUAL__VLM_ENABLED", "true")
    monkeypatch.setenv("HUGGINGFACE_TOKEN", "hf_dummy_test_token")
    monkeypatch.setenv("AURALYNQ_AIR_GAPPED", "false")
    reload_settings()
    vlm = get_vlm()  # constructs the client, no network call
    assert isinstance(vlm, HuggingFaceVLM)
    assert vlm.model == get_settings().visual.vlm_model


# ------------------------------------------------------- message construction


def test_encode_image_is_data_uri(tmp_path):
    p = tmp_path / "page_0001.png"
    _png(p)
    uri = encode_image(p)
    assert uri.startswith("data:image/png;base64,")


def test_vlm_builds_multimodal_message(tmp_path, monkeypatch):
    p1 = tmp_path / "a.png"
    p2 = tmp_path / "b.png"
    _png(p1)
    _png(p2)
    captured = {}

    class _FakeCompletions:
        def create(self, **kw):
            captured.update(kw)

            class _M:
                content = "Revenue grew (Page 1)."

            class _C:
                message = _M()

            class _R:
                choices = [_C()]

            return _R()

    vlm = HuggingFaceVLM.__new__(HuggingFaceVLM)
    vlm.model = "Qwen/Qwen2.5-VL-72B-Instruct"
    vlm._client = type("X", (), {"chat": type("Y", (), {"completions": _FakeCompletions()})()})()

    out = vlm.answer("What is the revenue trend?", [p1, p2], max_tokens=64)
    assert out == "Revenue grew (Page 1)."
    msgs = captured["messages"]
    assert msgs[0]["role"] == "system"
    user = msgs[1]["content"]
    # text question + (label + image) per page
    kinds = [b["type"] for b in user]
    assert kinds == ["text", "text", "image_url", "text", "image_url"]
    assert user[2]["image_url"]["url"].startswith("data:image/png;base64,")


# ------------------------------------------------------------- orchestration


class _FakeVLM:
    model = "fake-vlm"

    def __init__(self):
        self.calls = []

    def answer(self, question, image_paths, **kw):
        self.calls.append((question, list(image_paths)))
        return "The chart shows an upward trend (Page 1)."


class _FakeRetriever:
    def __init__(self, chunks):
        self._chunks = chunks

    def retrieve(self, query, k):
        return RetrievalResult(query=query, method="visual", chunks=self._chunks)


def _scored(doc_id, page):
    c = Chunk(
        id=f"{doc_id}-{page}",
        doc_id=doc_id,
        text="x",
        ordinal=0,
        source="deck.pdf",
        source_type=SourceType.pdf,
        span=SourceSpan(page=page),
    )
    return ScoredChunk(chunk=c, score=0.9, method="visual", rank=0)


def test_orchestration_resolves_pages_and_calls_vlm(monkeypatch):
    s = get_settings()
    doc_id = "doc1"
    cache = s.page_cache_dir / doc_id
    cache.mkdir(parents=True, exist_ok=True)
    _png(cache / "page_0002.png")

    fake_vlm = _FakeVLM()
    retriever = _FakeRetriever([_scored(doc_id, 2)])
    va = answer_visual_question("trend?", 6, settings=s, retriever=retriever, vlm=fake_vlm)

    assert va.available is True
    assert len(va.pages) == 1
    assert va.pages[0].page == 2
    assert "(Page 1)" in va.answer
    assert fake_vlm.calls[0][1][0].name == "page_0002.png"


def test_orchestration_unavailable_when_no_vlm(monkeypatch):
    monkeypatch.setenv("AURALYNQ_VISUAL__VLM_ENABLED", "false")
    reload_settings()
    va = answer_visual_question("trend?", 6, retriever=_FakeRetriever([]))
    assert va.available is False
    assert va.reason == "vlm_unavailable"


def test_orchestration_no_pages_returns_insufficient(monkeypatch):
    s = get_settings()
    # A chunk whose page image was never rendered → no resolvable pages.
    retriever = _FakeRetriever([_scored("missing_doc", 5)])
    va = answer_visual_question("trend?", 6, settings=s, retriever=retriever, vlm=_FakeVLM())
    assert va.available is True
    assert va.reason == "no_pages"
    assert "not contain enough information" in va.answer
