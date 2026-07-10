"""Synthesize Compounding-Wiki entity pages from the knowledge graph.

Reuses the PathRAG KG (entities + relations + full provenance) — no re-extraction.
For each qualifying entity we gather its relations and supporting chunk text and
have the LLM compile a durable, cited markdown page. Runs at ingest time; failures
are non-fatal (the wiki is additive and never blocks indexing).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from auralynq.config import get_settings
from auralynq.llm.base import Context
from auralynq.telemetry import get_logger
from auralynq.wiki.store import WikiStore

if TYPE_CHECKING:
    from auralynq.config.settings import WikiSettings
    from auralynq.ingest.models import Chunk
    from auralynq.llm.base import LLM
    from auralynq.retrieval.pathrag.graph import KnowledgeGraph

_log = get_logger("auralynq.wiki")

WIKI_SYSTEM = (
    "You are Auralynq's wiki compiler. Write a concise, durable encyclopedia-style "
    "page about the given entity using ONLY the numbered evidence provided. "
    "Rules:\n"
    "1. Start with a one-sentence definition of the entity.\n"
    "2. Then a short '## Summary' of what the sources say, citing every claim with "
    "[n] markers.\n"
    "3. Then '## Key relations' as a bullet list of the provided relations, each "
    "with its citation.\n"
    "4. Use [[Other Entity]] wiki-links when you mention another named entity.\n"
    "5. Never invent facts or add anything not supported by the evidence. "
    "If evidence is thin, keep the page short.\n"
    "Output GitHub-flavored markdown only — no frontmatter, no title heading."
)


def _entity_relations(kg: KnowledgeGraph, key: str) -> list[str]:
    """Human-readable relation lines for an entity, both directions, with a
    reliability score and its distinct source count."""
    name_of = lambda k: kg.g.nodes[k].get("name", k) if kg.g.has_node(k) else k  # noqa: E731
    out: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for _, dst, data in kg.g.out_edges(key, data=True):
        d = data.get("_dst", dst)
        sig = (key, data.get("relation", ""), d)
        if sig in seen:
            continue
        seen.add(sig)
        srcs = {getattr(p, "source", "") for p in data.get("provenance", [])}
        out.append(
            f"[[{name_of(key)}]] {data.get('relation', '—')} [[{name_of(d)}]] "
            f"(reliability {data.get('reliability', 0.0):.2f}, {len(srcs)} source(s))"
        )
    for src, _, data in kg.g.in_edges(key, data=True):
        sig = (src, data.get("relation", ""), key)
        if sig in seen:
            continue
        seen.add(sig)
        srcs = {getattr(p, "source", "") for p in data.get("provenance", [])}
        out.append(
            f"[[{name_of(src)}]] {data.get('relation', '—')} [[{name_of(key)}]] "
            f"(reliability {data.get('reliability', 0.0):.2f}, {len(srcs)} source(s))"
        )
    return out


def _evidence(
    chunk_ids: list[str], chunk_by_id: dict[str, Chunk], budget_chars: int
) -> tuple[list[Context], list[str]]:
    """Build numbered evidence Contexts (capped by char budget) + distinct sources."""
    contexts: list[Context] = []
    sources: set[str] = set()
    used = 0
    for cid in chunk_ids:
        c = chunk_by_id.get(cid)
        if c is None:
            continue
        text = (c.text or "").strip()
        if not text:
            continue
        if used + len(text) > budget_chars and contexts:
            break
        used += len(text)
        loc = c.locator() if hasattr(c, "locator") else ""
        contexts.append(
            Context(marker=len(contexts) + 1, text=text, source=c.source, locator=loc)
        )
        if c.source:
            sources.add(c.source)
    return contexts, sorted(sources)


def _build_prompt(name: str, relations: list[str], contexts: list[Context]) -> str:
    lines = [f"ENTITY: {name}", "", "EVIDENCE:"]
    for c in contexts:
        head = f"[{c.marker}]"
        if c.source:
            head += f"  ({c.source}{' · ' + c.locator if c.locator else ''})"
        lines += [head, c.text, ""]
    if relations:
        lines += ["KNOWN RELATIONS (from the knowledge graph):"]
        lines += [f"- {r}" for r in relations]
        lines.append("")
    lines.append(f"Write the wiki page for [[{name}]] now.")
    return "\n".join(lines)


def _synthesize_one(
    kg: KnowledgeGraph,
    key: str,
    data: dict[str, Any],
    chunk_by_id: dict[str, Chunk],
    llm: LLM,
    store: WikiStore,
    w: WikiSettings,
) -> bool:
    name = data.get("name", key)
    chunk_ids = sorted(data.get("chunk_ids", set()))
    contexts, sources = _evidence(chunk_ids, chunk_by_id, w.max_context_chars)
    if not contexts:
        return False
    relations = _entity_relations(kg, key)
    prompt = _build_prompt(name, relations, contexts)
    try:
        body = llm.generate(
            prompt, system=WIKI_SYSTEM, temperature=0.2, max_tokens=w.max_page_tokens
        ).strip()
    except Exception as e:  # pragma: no cover - provider failure is non-fatal
        _log.warning("wiki.page_generate_failed", entity=key, error=str(e))
        return False
    if not body:
        return False
    store.write_page(
        key,
        title=name,
        body=body,
        page_type="entity",
        sources=sources,
        mentions=int(data.get("mentions", 0)),
    )
    return True


def synthesize_wiki(
    kg: KnowledgeGraph,
    chunks: list[Chunk],
    *,
    llm: LLM | None = None,
    settings: Any | None = None,
) -> int:
    """Synthesize/refresh entity pages from the KG. Returns pages written.

    Selects entities with >= ``min_mentions`` mentions, highest-mention first,
    capped at ``max_entities`` per run (cost guard).
    """
    s = settings or get_settings()
    w = s.wiki
    if llm is None:
        from auralynq.llm.factory import get_llm

        llm = get_llm()
    store = WikiStore(s.wiki_dir)
    chunk_by_id: dict[str, Chunk] = {c.id: c for c in chunks}

    ents = [
        (key, data)
        for key, data in kg.g.nodes(data=True)
        if data.get("mentions", 0) >= w.min_mentions
    ]
    ents.sort(key=lambda kd: kd[1].get("mentions", 0), reverse=True)
    ents = ents[: w.max_entities]

    written = 0
    for key, data in ents:
        if _synthesize_one(kg, key, data, chunk_by_id, llm, store, w):
            written += 1

    store.append_log(
        "synthesize", entities_considered=len(ents), pages_written=written
    )
    _log.info("wiki.synthesized", entities=len(ents), pages_written=written)
    return written
