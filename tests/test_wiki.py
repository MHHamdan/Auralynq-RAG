from __future__ import annotations

from auralynq.config.settings import Settings
from auralynq.ingest.models import Chunk, SourceType
from auralynq.retrieval.pathrag.builder import build_from_chunks
from auralynq.wiki.generator import synthesize_wiki
from auralynq.wiki.store import WikiStore, slug


class _StubLLM:
    """Deterministic stand-in for a provider — no network, no model."""

    name = "stub"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate(self, prompt: str, *, system=None, temperature=None, max_tokens=None) -> str:
        self.calls.append(prompt)
        return "One-sentence definition.\n\n## Summary\nThe sources describe it [1].\n"


def _chunks() -> list[Chunk]:
    return [
        Chunk(id="c0", doc_id="d", ordinal=0, source="geo.txt", source_type=SourceType.text,
              text="Paris is the capital of France. France is in Europe."),
        Chunk(id="c1", doc_id="d", ordinal=1, source="geo2.txt", source_type=SourceType.text,
              text="Paris is the capital of France and a large city."),
    ]


def test_slug_is_filesystem_safe_and_stable():
    assert slug("GPT-4 / Turbo!") == "gpt_4_turbo"
    assert slug("  Hello World  ") == "hello_world"
    long = "x" * 200
    assert len(slug(long)) <= 64 and slug(long) == slug(long)


def test_wiki_store_roundtrip(tmp_path):
    store = WikiStore(tmp_path / "wiki_pages")
    meta = store.write_page(
        "paris", title="Paris", body="Capital of France [1].",
        sources=["geo.txt", "geo2.txt"], mentions=3,
    )
    assert meta.path == "entity_paris.md"
    page = store.read_page("paris")
    assert page is not None
    assert "title: \"Paris\"" in page["markdown"]
    assert "Capital of France [1]." in page["markdown"]
    assert page["mentions"] == 3
    listed = store.list_pages()
    assert any(p["id"] == "paris" for p in listed)
    assert store.count() == 1
    store.append_log("test", n=1)
    assert (tmp_path / "wiki_pages" / "_log.jsonl").exists()


def test_read_missing_page_returns_none(tmp_path):
    assert WikiStore(tmp_path / "w").read_page("nope") is None


def test_synthesize_wiki_from_kg(tmp_path):
    s = Settings(data_dir=tmp_path)
    s.wiki.enabled = True
    s.wiki.min_mentions = 1
    kg = build_from_chunks(_chunks())
    llm = _StubLLM()

    written = synthesize_wiki(kg, _chunks(), llm=llm, settings=s)

    assert written >= 1
    assert llm.calls, "LLM was invoked for synthesis"
    store = WikiStore(s.wiki_dir)
    assert store.count() == written
    paris = store.read_page("paris")
    assert paris is not None
    # Frontmatter carries the source provenance from the entity's chunks.
    assert "geo.txt" in paris["markdown"]
    assert "## Summary" in paris["markdown"]


def test_wiki_disabled_by_default():
    assert Settings().wiki.enabled is False


def test_min_mentions_gate(tmp_path):
    s = Settings(data_dir=tmp_path)
    s.wiki.enabled = True
    s.wiki.min_mentions = 999  # gate everything out
    kg = build_from_chunks(_chunks())
    assert synthesize_wiki(kg, _chunks(), llm=_StubLLM(), settings=s) == 0


def test_wiki_retriever_matches_entity(tmp_path):
    from auralynq.wiki.retriever import WikiRetriever

    store = WikiStore(tmp_path / "w")
    store.write_page("auralynq", title="Auralynq",
                     body="## Summary\nAuralynq fuses dense and sparse vectors [1][2].",
                     sources=["a.md"], mentions=3)
    store.write_page("france", title="France", body="Country in Europe [1].", mentions=2)

    res = WikiRetriever(tmp_path / "w").retrieve("Tell me about Auralynq", k=2)
    assert res.chunks, "matched the Auralynq page"
    top = res.chunks[0]
    assert top.method == "wiki"
    assert top.chunk.source == "Auralynq (wiki)"
    # Internal [n] markers are stripped so they don't clash with answer citations.
    assert "[1]" not in top.chunk.text and "[2]" not in top.chunk.text
    assert "fuses dense and sparse" in top.chunk.text


def test_wiki_retriever_no_match_is_empty(tmp_path):
    from auralynq.wiki.retriever import WikiRetriever

    store = WikiStore(tmp_path / "w")
    store.write_page("france", title="France", body="A country.", mentions=2)
    res = WikiRetriever(tmp_path / "w").retrieve("quantum chromodynamics gluons", k=2)
    assert res.chunks == []
