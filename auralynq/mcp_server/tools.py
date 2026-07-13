"""Auralynq MCP tool implementations (transport-agnostic).

These plain functions are what the ``auralynq-mcp`` server exposes. Keeping them
free of MCP-SDK types means they are unit-testable directly and reusable from the
CLI/API. ``server.py`` registers them with the MCP SDK.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def ingest_documents(path: str, recursive: bool = True) -> dict[str, Any]:
    """Ingest and index a file or directory; returns index statistics."""
    from auralynq.pipeline import build_index

    return build_index(Path(path), rebuild=False)


def search(query: str, k: int = 6) -> dict[str, Any]:
    """Hybrid dense+sparse search; returns scored chunks with citations."""
    from auralynq.retrieval.hybrid.retriever import HybridRetriever

    res = HybridRetriever().retrieve(query, k)
    return {
        "query": query,
        "method": res.method,
        "results": [
            {"score": round(c.score, 4), "text": c.chunk.text, "citation": c.chunk.citation()}
            for c in res.chunks
        ],
    }


def graph_path_query(query: str, k: int = 6) -> dict[str, Any]:
    """PathRAG relational path retrieval; returns evidence paths + citations."""
    from auralynq.pipeline import load_graph
    from auralynq.retrieval.pathrag.retriever import PathRAGRetriever

    res = PathRAGRetriever(load_graph()).retrieve(query, k)
    return {
        "query": query,
        "seeds": res.metadata.get("seeds", []),
        "paths": res.metadata.get("paths", []),
        "results": [{"text": c.chunk.text, "citation": c.chunk.citation()} for c in res.chunks],
    }


def transcribe(audio_path: str, diarize: bool = True) -> dict[str, Any]:
    """Transcribe (and optionally diarize) an audio file."""
    from auralynq.voice.loop import transcribe as _t

    t = _t(Path(audio_path), diarize=diarize)
    return {
        "language": t.language,
        "provider": t.provider,
        "text": t.text,
        "segments": [
            {"start_s": s.start_s, "end_s": s.end_s, "speaker": s.speaker, "text": s.text}
            for s in t.segments
        ],
    }


def talk_to_data(question: str, final_k: int | None = None) -> dict[str, Any]:
    """Full agentic answer with citations, route and path evidence."""
    from auralynq.agent.runner import answer_question

    return answer_question(question, final_k=final_k).to_dict()


def run_eval(smoke: bool = True) -> dict[str, Any]:
    """Run the evaluation harness and return metrics."""
    from auralynq.eval.report import run_eval as _run

    return _run(smoke=smoke, write_report=not smoke)


def get_trace(question: str) -> dict[str, Any]:
    """Run the agent and return only the trace trajectory (spans + timings)."""
    from auralynq.agent.runner import answer_question

    res = answer_question(question, use_cache=False)
    return {
        "question": question,
        "route": res.route,
        "elapsed_ms": res.elapsed_ms,
        "trace": res.trace,
    }


# ---------------------------------------------------------- memory tier ------
# Turns Auralynq into an agent-memory backend: external agents `remember` durable
# notes and `recall` them later. Backed by the compounding wiki (type="memory"),
# so memories persist across sessions and live beside the rest of the knowledge.
_MEMORY_TYPE = "memory"


def remember(text: str, tags: list[str] | None = None, source: str = "agent") -> dict[str, Any]:
    """Store a durable memory for later recall. Returns its id (idempotent per text)."""
    from auralynq.config.settings import get_settings
    from auralynq.utils import stable_id
    from auralynq.wiki.store import WikiStore

    text = (text or "").strip()
    if not text:
        return {"stored": False, "reason": "empty text"}
    store = WikiStore(get_settings().wiki_dir)
    mem_id = "mem_" + stable_id(text)[:12]
    store.write_page(
        mem_id,
        title=text[:120],
        body=text,
        page_type=_MEMORY_TYPE,
        sources=[source, *(tags or [])],
    )
    return {"stored": True, "id": mem_id}


def recall(query: str, k: int = 5) -> dict[str, Any]:
    """Recall stored memories most relevant to the query (content token overlap)."""
    from auralynq.config.settings import get_settings
    from auralynq.utils import tokenize
    from auralynq.wiki.generator import _strip_frontmatter
    from auralynq.wiki.store import WikiStore

    store = WikiStore(get_settings().wiki_dir)
    q = {t for t in tokenize(query or "") if len(t) > 2}
    scored: list[tuple[float, str, str, list[str]]] = []
    for meta in store.list_pages():
        if meta.get("type") != _MEMORY_TYPE:
            continue
        page = store.read_page(str(meta["id"]))
        body = _strip_frontmatter(page.get("markdown", "")) if page else ""
        toks = {t for t in tokenize(body) if len(t) > 2}
        overlap = len(q & toks)
        if overlap == 0:
            continue
        score = overlap / max(len(q), 1)
        scored.append(
            (round(score, 3), str(meta["id"]), body.strip(), meta.get("sources", []) or [])
        )
    scored.sort(key=lambda s: s[0], reverse=True)
    return {
        "query": query,
        "memories": [
            {"id": mid, "text": body, "score": sc, "sources": srcs}
            for sc, mid, body, srcs in scored[:k]
        ],
    }


TOOLS = {
    "ingest_documents": ingest_documents,
    "search": search,
    "graph_path_query": graph_path_query,
    "transcribe": transcribe,
    "talk_to_data": talk_to_data,
    "run_eval": run_eval,
    "get_trace": get_trace,
    "remember": remember,
    "recall": recall,
}
