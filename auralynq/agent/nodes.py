"""Agent node functions (planner → … → citation validator).

Each node takes the shared :class:`AgentState` and :class:`AgentDeps`, wraps its
work in a trace span, and mutates/returns state. The same functions are used by
both the LangGraph executor and the native fallback executor (ADR-0008).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from auralynq.agent.state import AgentState
from auralynq.config import Settings
from auralynq.llm.base import LLM, Context
from auralynq.retrieval.hybrid.fusion import reciprocal_rank_fusion
from auralynq.retrieval.hybrid.reorder import lost_in_the_middle_reorder
from auralynq.retrieval.hybrid.retriever import HybridRetriever
from auralynq.retrieval.models import Filter, ScoredChunk
from auralynq.retrieval.pathrag.graph import KnowledgeGraph
from auralynq.retrieval.pathrag.retriever import PathRAGRetriever
from auralynq.retrieval.router import Route, route_query
from auralynq.telemetry.tracing import Trace
from auralynq.utils import tokenize

_MARKER_RE = re.compile(r"\[(\d+)\]")
_STOP = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "of",
    "to",
    "in",
    "on",
    "and",
    "or",
    "how",
    "what",
    "why",
    "who",
    "where",
    "when",
    "does",
    "do",
    "did",
    "between",
    "with",
}


@dataclass
class AgentDeps:
    hybrid: HybridRetriever
    pathrag: PathRAGRetriever
    llm: LLM
    graph: KnowledgeGraph
    trace: Trace
    settings: Settings
    filt: Filter | None = None


def node_plan(state: AgentState, deps: AgentDeps) -> AgentState:
    with deps.trace.span("planner", question=state.question) as sp:
        if not state.original_question:
            state.original_question = state.question
        sp.attributes["final_k"] = state.final_k
    return state


def node_route(state: AgentState, deps: AgentDeps) -> AgentState:
    with deps.trace.span("router") as sp:
        decision = route_query(state.question, deps.graph)
        state.route = decision.route
        state.route_confidence = decision.confidence
        state.route_rationale = decision.rationale
        sp.attributes.update(
            route=decision.route.value, confidence=decision.confidence, rationale=decision.rationale
        )
    return state


def node_retrieve(state: AgentState, deps: AgentDeps) -> AgentState:
    pool_k = max(state.final_k * 2, deps.settings.retrieval.top_k)
    if state.route in (Route.fast, Route.hybrid):
        with deps.trace.span("hybrid_retriever") as sp:
            res = deps.hybrid.retrieve(state.question, pool_k, deps.filt)
            state.contexts.extend(res.chunks)
            sp.attributes.update(n=len(res.chunks), stages=str(res.metadata))
    if state.route in (Route.graph, Route.hybrid):
        with deps.trace.span("pathrag_retriever") as sp:
            res = deps.pathrag.retrieve(state.question, pool_k, deps.filt)
            state.contexts.extend(res.chunks)
            state.path_evidence = [_ev(e) for e in res.metadata.get("paths", [])]
            state.seeds = res.metadata.get("seeds", [])
            sp.attributes.update(
                n=len(res.chunks), seeds=state.seeds, paths=len(state.path_evidence)
            )
    return state


def node_fuse(state: AgentState, deps: AgentDeps) -> AgentState:
    with deps.trace.span("context_fusion") as sp:
        by_method: dict[str, list[ScoredChunk]] = {}
        for c in state.contexts:
            by_method.setdefault(c.method, []).append(c)
        for lst in by_method.values():
            lst.sort(key=lambda c: c.score, reverse=True)
        fused = reciprocal_rank_fusion(
            list(by_method.values()), k=deps.settings.retrieval.rrf_k, top_k=state.final_k
        )
        fused = lost_in_the_middle_reorder(fused)
        state.contexts = fused
        sp.attributes.update(methods=list(by_method.keys()), final=len(fused))
    return state


def node_critic(state: AgentState, deps: AgentDeps) -> AgentState:
    with deps.trace.span("evidence_gap_critic") as sp:
        q_terms = {t for t in tokenize(state.original_question) if t not in _STOP and len(t) > 2}
        covered = set()
        for c in state.contexts:
            covered |= set(tokenize(c.chunk.text))
        missing = sorted(q_terms - covered)
        coverage = 1.0 - (len(missing) / max(len(q_terms), 1))
        state.gaps = missing
        state.coverage = round(coverage, 3)
        can_retry = (
            state.iteration < state.max_iters - 1
            and not state.out_of_budget()
            and len(state.contexts) >= 0
        )
        state.need_rewrite = bool(missing) and coverage < 0.6 and can_retry
        sp.attributes.update(
            coverage=round(coverage, 3), missing=missing, need_rewrite=state.need_rewrite
        )
    return state


def node_rewrite(state: AgentState, deps: AgentDeps) -> AgentState:
    with deps.trace.span("query_rewrite") as sp:
        state.iteration += 1
        extra = " ".join(state.gaps[:5] + state.seeds[:3])
        state.question = f"{state.original_question} {extra}".strip()
        state.contexts = []  # re-retrieve fresh on the rewritten query
        state.need_rewrite = False
        sp.attributes.update(iteration=state.iteration, rewritten=state.question)
    return state


def _contexts_for_llm(state: AgentState) -> list[Context]:
    out: list[Context] = []
    for i, c in enumerate(state.contexts, start=1):
        cit = c.chunk.citation()
        out.append(
            Context(
                marker=i, text=c.chunk.text, source=str(cit["source"]), locator=str(cit["locator"])
            )
        )
    return out


def node_synthesize(state: AgentState, deps: AgentDeps) -> AgentState:
    with deps.trace.span("synthesizer", provider=deps.llm.name) as sp:
        contexts = _contexts_for_llm(state)
        if not contexts:
            state.answer = "I don't have enough evidence in the indexed sources to answer that."
        else:
            state.answer = deps.llm.answer(
                state.original_question,
                contexts,
                temperature=deps.settings.llm.temperature,
                max_tokens=deps.settings.llm.max_tokens,
            ).strip()
        sp.attributes["chars"] = len(state.answer)
    return state


def node_self_check(state: AgentState, deps: AgentDeps) -> AgentState:
    with deps.trace.span("self_check") as sp:
        markers = {int(m) for m in _MARKER_RE.findall(state.answer)}
        valid = {m for m in markers if 1 <= m <= len(state.contexts)}
        has_support = bool(valid) or not state.contexts
        if not has_support and state.contexts:
            state.notes.append("answer lacked citations; flagged low confidence")
        state.confidence = round(
            0.4 * min(len(state.contexts) / max(state.final_k, 1), 1.0)
            + 0.3 * (1.0 if valid else 0.0)
            + 0.3 * (1.0 - len(state.gaps) / max(len(tokenize(state.original_question)), 1)),
            3,
        )
        sp.attributes.update(citations_used=sorted(valid), confidence=state.confidence)
    return state


def node_validate_citations(state: AgentState, deps: AgentDeps) -> AgentState:
    with deps.trace.span("citation_validator") as sp:
        used = sorted(
            {int(m) for m in _MARKER_RE.findall(state.answer) if 1 <= int(m) <= len(state.contexts)}
        )

        # Drop dangling markers that point outside the context set.
        def _scrub(match: re.Match) -> str:
            n = int(match.group(1))
            return match.group(0) if 1 <= n <= len(state.contexts) else ""

        state.answer = _MARKER_RE.sub(_scrub, state.answer).strip()
        citations = []
        for n in used:
            cit = state.contexts[n - 1].chunk.citation()
            cit["marker"] = n
            citations.append(cit)
        state.citations = citations
        sp.attributes.update(n_citations=len(citations))
    return state


def _ev(d: dict):
    from auralynq.retrieval.models import PathEvidence

    return PathEvidence.model_validate(d)
