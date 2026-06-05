"""Adaptive router: decide fast hybrid vs. PathRAG vs. both.

Heuristic, explainable, and deterministic (ADR-0008). Signals:
* relational/multi-hop language ("between", "compare", "relationship", "both", …)
* multiple distinct entities present in the query
* how many of those entities exist in the knowledge graph
* query length / question structure

Returns a :class:`RouteDecision` with the route, confidence and a human-readable
rationale, which is surfaced in the trace panel. An optional LLM classifier can be
layered behind the same interface later; the heuristic is the $0 default.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from auralynq.retrieval.pathrag.graph import KnowledgeGraph
from auralynq.utils import tokenize

_RELATIONAL = re.compile(
    r"\b(between|relationship|related|connect|compare|comparison|both|versus|vs|"
    r"link|cause|because|why|how does|influence|affect|chain|path|trace|"
    r"multi-?hop|across|through|via|lead to|result)\b",
    re.IGNORECASE,
)
_ENTITY_RE = re.compile(r"\b[A-Z][\w’’-]*(?:\s+[A-Z][\w’’-]*)*\b")
_SIMPLE_LEAD = re.compile(r"^(what is|who is|define|when|where|list|give me)\b", re.IGNORECASE)
# Factoid patterns: single-entity declarations, pledges, policy statements.
# Their multi-entity surface form fools the entity counter into thinking they are
# relational, but they are simple retrieval questions, not multi-hop traversals.
_FACTOID = re.compile(
    r"\b(pledge|pledged|pledges|policy|policies|announced|announcement|statement|"
    r"committed|commitment|promise|promis|declared|declaration|press.?release|"
    r"what did|status)\b",
    re.IGNORECASE,
)


class Route(str, Enum):
    fast = "fast"  # hybrid only
    graph = "graph"  # PathRAG only
    hybrid = "hybrid"  # both, fused


@dataclass
class RouteDecision:
    route: Route
    confidence: float
    rationale: str
    signals: dict[str, float]


def route_query(query: str, graph: KnowledgeGraph | None = None) -> RouteDecision:
    relational_hits = len(_RELATIONAL.findall(query))
    factoid_hits = len(_FACTOID.findall(query))
    entities = [e.strip() for e in _ENTITY_RE.findall(query) if len(e.strip()) > 2]
    distinct_entities = len({e.lower() for e in entities})
    in_graph = sum(1 for e in entities if graph is not None and graph.has(e))
    n_tokens = len(tokenize(query))
    simple_lead = bool(_SIMPLE_LEAD.match(query.strip()))

    signals = {
        "relational_hits": float(relational_hits),
        "factoid_hits": float(factoid_hits),
        "distinct_entities": float(distinct_entities),
        "entities_in_graph": float(in_graph),
        "tokens": float(n_tokens),
        "simple_lead": 1.0 if simple_lead else 0.0,
    }

    # Scoring: graph evidence pushes toward PathRAG; simple lexical lookups stay fast.
    # factoid_hits dampen graph routing for pledge/policy/announcement queries whose
    # multi-entity surface form would otherwise look relational.
    graph_score = relational_hits * 1.2 + max(distinct_entities - 1, 0) * 0.8 + in_graph * 0.6
    fast_score = (
        (1.5 if simple_lead else 0.0)
        + (1.0 if distinct_entities <= 1 else 0.0)
        + factoid_hits * 1.2  # each factoid cue adds fast-path weight
    )

    if graph_score >= 2.0 and in_graph >= 1:
        route, conf = Route.graph, min(0.5 + graph_score / 6.0, 0.95)
        why = (
            f"{relational_hits} relational cue(s), {distinct_entities} entities "
            f"({in_graph} in graph) → multi-hop PathRAG"
        )
    elif graph_score >= 1.0 and fast_score < 2.0:
        route, conf = Route.hybrid, 0.6
        why = "uncertain (some relational signal but weak graph grounding) → hybrid of both"
    else:
        route, conf = Route.fast, min(0.6 + fast_score / 4.0, 0.95)
        why = "simple/factoid lookup → fast hybrid retrieval"

    return RouteDecision(route=route, confidence=round(conf, 3), rationale=why, signals=signals)
