"""High-level agent entry points used by the CLI, API and MCP server."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel, Field

from auralynq.agent.cache import SemanticCache
from auralynq.agent.graph import run_agent
from auralynq.agent.nodes import (
    AgentDeps,
    _contexts_for_llm,
    node_critic,
    node_fuse,
    node_plan,
    node_retrieve,
    node_rewrite,
    node_route,
    node_self_check,
    node_validate_citations,
)
from auralynq.agent.state import AgentState
from auralynq.config import get_settings
from auralynq.llm.factory import get_llm
from auralynq.pipeline import load_graph
from auralynq.retrieval.hybrid.retriever import HybridRetriever
from auralynq.retrieval.models import Filter
from auralynq.retrieval.pathrag.retriever import PathRAGRetriever
from auralynq.telemetry.tracing import Trace
from auralynq.utils import stable_id

_CACHE = SemanticCache()


def _export_langfuse(trace: Trace, question: str, answer: str, metadata: dict) -> None:
    """Best-effort hosted-trace export; never affects the response (ADR-0019)."""
    try:
        from auralynq.telemetry.langfuse_export import export_trace

        export_trace(trace, question=question, answer=answer, metadata=metadata)
    except Exception:  # pragma: no cover - observability must not break answers
        pass


class AnswerResult(BaseModel):
    answer: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    route: str = "fast"
    route_confidence: float = 0.0
    route_rationale: str = ""
    path_evidence: list[dict[str, Any]] = Field(default_factory=list)
    seeds: list[str] = Field(default_factory=list)
    iterations: int = 0
    confidence: float = 0.0
    cached: bool = False
    elapsed_ms: float = 0.0
    contexts: list[str] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


def _build_deps(trace: Trace, filt: Filter | None) -> AgentDeps:
    s = get_settings()
    graph = load_graph()
    hybrid = HybridRetriever()
    return AgentDeps(
        hybrid=hybrid,
        pathrag=PathRAGRetriever(graph, store=hybrid.store, embedder=hybrid.embedder),
        llm=get_llm(),
        graph=graph,
        trace=trace,
        settings=s,
        filt=filt,
    )


def _new_state(question: str, final_k: int | None) -> AgentState:
    s = get_settings()
    return AgentState(
        question=question,
        original_question=question,
        final_k=final_k or s.retrieval.final_k,
        max_iters=s.agent.max_iters,
        latency_budget_ms=s.agent.latency_budget_ms,
    )


def answer_question(
    question: str,
    final_k: int | None = None,
    filt: Filter | None = None,
    use_cache: bool | None = None,
) -> AnswerResult:
    s = get_settings()
    use_cache = s.agent.semantic_cache if use_cache is None else use_cache
    trace = Trace(trace_id=stable_id(question))

    if use_cache:
        hit = _CACHE.lookup(question)
        if hit is not None:
            answer, citations = hit
            return AnswerResult(
                answer=answer, citations=citations, cached=True, trace=trace.to_list()
            )

    deps = _build_deps(trace, filt)
    state = _new_state(question, final_k)
    state = run_agent(state, deps)

    result = AnswerResult(
        answer=state.answer,
        citations=state.citations,
        route=state.route.value,
        route_confidence=state.route_confidence,
        route_rationale=state.route_rationale,
        path_evidence=[e.model_dump() for e in state.path_evidence],
        seeds=state.seeds,
        iterations=state.iteration,
        confidence=state.confidence,
        elapsed_ms=round(trace.total_ms, 2),
        contexts=[c.chunk.text for c in state.contexts],
        trace=trace.to_list(),
    )
    if use_cache and state.answer:
        _CACHE.store(question, state.answer, state.citations)
    _export_langfuse(
        trace,
        question,
        state.answer,
        {
            "route": state.route.value,
            "confidence": state.confidence,
            "iterations": state.iteration,
            "cached": False,
        },
    )
    return result


def stream_answer_question(
    question: str, final_k: int | None = None, filt: Filter | None = None
) -> Iterator[dict[str, Any]]:
    """Yield SSE-style events: {'type': 'token'|'meta'|'final', ...}."""
    trace = Trace(trace_id=stable_id(question))
    deps = _build_deps(trace, filt)
    state = _new_state(question, final_k)

    # Run retrieval + fusion + critic/rewrite loop (non-streamed).
    state = node_plan(state, deps)
    while True:
        state = node_route(state, deps)
        state = node_retrieve(state, deps)
        state = node_fuse(state, deps)
        state = node_critic(state, deps)
        state.elapsed_ms = trace.total_ms
        if state.need_rewrite and not state.out_of_budget():
            state = node_rewrite(state, deps)
            continue
        break

    yield {
        "type": "meta",
        "route": state.route.value,
        "confidence": state.route_confidence,
        "rationale": state.route_rationale,
        "seeds": state.seeds,
        "path_evidence": [e.model_dump() for e in state.path_evidence],
    }

    contexts = _contexts_for_llm(state)
    acc = []
    with trace.span("synthesizer_stream", provider=deps.llm.name):
        if not contexts:
            msg = "I don't have enough evidence in the indexed sources to answer that."
            acc.append(msg)
            yield {"type": "token", "text": msg}
        else:
            for tok in deps.llm.stream_answer(
                state.original_question,
                contexts,
                temperature=deps.settings.llm.temperature,
                max_tokens=deps.settings.llm.max_tokens,
            ):
                acc.append(tok)
                yield {"type": "token", "text": tok}

    state.answer = "".join(acc).strip()
    state = node_self_check(state, deps)
    state = node_validate_citations(state, deps)
    _export_langfuse(
        trace,
        question,
        state.answer,
        {"route": state.route.value, "confidence": state.confidence, "streamed": True},
    )
    yield {
        "type": "final",
        "answer": state.answer,
        "citations": state.citations,
        "confidence": state.confidence,
        "elapsed_ms": round(trace.total_ms, 2),
        "trace": trace.to_list(),
    }
