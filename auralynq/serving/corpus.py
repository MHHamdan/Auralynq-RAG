"""Corpus introspection: what is actually indexed, and corpus-aware suggestions.

The frontend must never guess what to suggest. These helpers read the live
knowledge graph + vector store so example questions and the empty/insufficient
states reflect the *real* corpus (e.g. medical/infection topics) rather than
stale hardcoded geography chips. Everything degrades to safe defaults when the
index is empty or a backend is unavailable (ADR-0003/0004).
"""

from __future__ import annotations

import re
import time
from collections import Counter
from typing import Any

from auralynq.config import get_settings

# corpus_summary() runs on every query (suggestions + entity detection), so cache
# it briefly — the index changes only on ingest, never mid-query.
_CACHE_TTL_S = 30.0
_cache: dict[str, Any] = {"at": 0.0, "value": None}

# Entity names too generic to drive a useful suggestion or "detected entity".
_GENERIC = {
    "answers",
    "answer",
    "each",
    "hybrid",
    "data",
    "document",
    "documents",
    "section",
    "thing",
    "things",
    "system",
}
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9-]+")


def _graph_entities() -> list[dict[str, Any]]:
    """Top graph entities by mention count, cleaned of generic noise."""
    try:
        from auralynq.pipeline import load_graph

        kg = load_graph()
        rows: list[dict[str, Any]] = []
        for _key, attrs in kg.g.nodes(data=True):
            name = str(attrs.get("name") or "").strip()
            if not name:
                continue
            short = name.split()[0] if name else name
            if short.lower() in _GENERIC or len(name) < 2:
                continue
            rows.append(
                {
                    "name": name,
                    "type": str(attrs.get("type", "concept")),
                    "mentions": int(attrs.get("mentions", 0)),
                    "chunks": len(attrs.get("chunk_ids", []) or []),
                }
            )
        rows.sort(key=lambda r: (r["mentions"], r["chunks"]), reverse=True)
        # Deduplicate near-identical names (e.g. "Auralynq" / "Auralynq Auralynq").
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for r in rows:
            head = r["name"].split()[0].lower()
            if head in seen:
                continue
            seen.add(head)
            out.append(r)
        return out
    except Exception:  # pragma: no cover - defensive
        return []


def _store_facts() -> dict[str, Any]:
    """Distinct sources / source-types / vector count from the live store."""
    facts: dict[str, Any] = {"vectors": 0, "titles": [], "source_types": {}}
    try:
        from auralynq.vectorstore.factory import get_store

        store = get_store()
        try:
            facts["vectors"] = int(store.count())
        except Exception:  # pragma: no cover
            facts["vectors"] = 0
        chunks = store.all_chunks() or []
        titles: list[str] = []
        stype: Counter[str] = Counter()
        seen: set[str] = set()
        for c in chunks:
            src = (getattr(c, "title", None) or getattr(c, "source", "") or "").strip()
            st = getattr(getattr(c, "source_type", None), "value", None) or "unknown"
            stype[st] += 1
            if src and src not in seen:
                seen.add(src)
                titles.append(src)
        facts["titles"] = titles[:50]
        facts["source_types"] = dict(stype)
        # Remote stores (Qdrant) don't enumerate via all_chunks; scroll payload
        # metadata so doc count/types are honest instead of reading 0.
        if not titles and facts["vectors"] and hasattr(store, "document_facts"):
            df = store.document_facts()
            facts["titles"] = df.get("titles", [])
            facts["source_types"] = df.get("source_types", {})
    except Exception:  # pragma: no cover - defensive
        pass
    return facts


def _last_indexed() -> str | None:
    """ISO timestamp of the most recent index artifact, if any."""
    import datetime as _dt

    s = get_settings()
    newest = 0.0
    try:
        for p in s.index_dir.rglob("*"):
            if p.is_file():
                newest = max(newest, p.stat().st_mtime)
    except Exception:  # pragma: no cover
        return None
    if newest <= 0:
        return None
    return _dt.datetime.fromtimestamp(newest, tz=_dt.UTC).isoformat()


def corpus_summary(use_cache: bool = True) -> dict[str, Any]:
    """A structured, frontend-ready snapshot of what is indexed (TTL-cached)."""
    now = time.monotonic()
    if use_cache and _cache["value"] is not None and (now - _cache["at"]) < _CACHE_TTL_S:
        return _cache["value"]
    value = _corpus_summary_uncached()
    _cache["value"] = value
    _cache["at"] = now
    return value


def invalidate_corpus_cache() -> None:
    """Drop the cached summary — call after ingest so stats refresh immediately."""
    _cache["value"] = None
    _cache["at"] = 0.0


def _corpus_summary_uncached() -> dict[str, Any]:
    ents = _graph_entities()
    facts = _store_facts()
    doc_count = len(facts["titles"])
    # When the store can't enumerate chunks (remote Qdrant), fall back to graph
    # presence so the UI doesn't read "empty" while 1000s of vectors exist.
    indexed = bool(facts["vectors"]) or bool(ents) or doc_count > 0
    return {
        "indexed": indexed,
        "indexed_document_count": doc_count,
        "vector_count": facts["vectors"],
        "document_titles": facts["titles"],
        "source_types": facts["source_types"],
        "top_entities": ents[:12],
        "entity_count": len(ents),
        "last_indexed": _last_indexed(),
    }


def suggested_questions(limit: int = 3, summary: dict[str, Any] | None = None) -> list[str]:
    """Corpus-aware example questions built from the indexed entities.

    No hardcoded topic chips: if the corpus is medical the suggestions are about
    its entities; if nothing is indexed we return generic, corpus-neutral prompts.
    """
    summary = summary or corpus_summary()
    ents = [e["name"] for e in summary.get("top_entities", [])]
    out: list[str] = []
    if ents:
        out.append(f"What does the corpus say about {ents[0]}?")
        if len(ents) >= 2:
            out.append(f"How are {ents[0]} and {ents[1]} related?")
        if len(ents) >= 3:
            out.append(f"Summarize the key points about {ents[2]}.")
        out.append(f"What evidence supports claims about {ents[0]}?")
    # Always-valid, corpus-neutral fallbacks to pad to `limit`.
    for generic in (
        "Summarize the main topics in the indexed documents.",
        "What are the key entities and how do they relate?",
        "List the most important findings in the corpus.",
    ):
        if len(out) >= max(limit, 1):
            break
        if generic not in out:
            out.append(generic)
    # Dedup, preserve order.
    seen: set[str] = set()
    deduped: list[str] = []
    for q in out:
        if q not in seen:
            seen.add(q)
            deduped.append(q)
    return deduped[:limit]


def detect_entities(question: str, summary: dict[str, Any] | None = None) -> list[str]:
    """Question terms that match known corpus entities (case-insensitive)."""
    summary = summary or corpus_summary()
    known = {e["name"].lower(): e["name"] for e in summary.get("top_entities", [])}
    # Also index single-word heads so "Paris" matches "Geography Paris".
    heads: dict[str, str] = {}
    for e in summary.get("top_entities", []):
        for tok in _WORD.findall(e["name"]):
            heads.setdefault(tok.lower(), e["name"])
    found: list[str] = []
    seen: set[str] = set()
    q_tokens = [t.lower() for t in _WORD.findall(question)]
    qlow = question.lower()
    for name_l, name in known.items():
        if name_l in qlow and name not in seen:
            seen.add(name)
            found.append(name)
    for tok in q_tokens:
        if tok in heads and heads[tok] not in seen:
            seen.add(heads[tok])
            found.append(heads[tok])
    return found[:8]
