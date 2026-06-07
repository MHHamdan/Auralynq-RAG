"""Planned/stub strategies — registered but not yet implemented."""
from __future__ import annotations

from typing import Any

from auralynq.rag.strategies.base import RAGStrategy, StrategyResult


def _not_implemented(strategy_id: str, strategy_name: str, query: str) -> StrategyResult:
    return StrategyResult(
        answer=(
            f"The **{strategy_name}** strategy is planned but not yet implemented. "
            "Falling back to Auralynq-RAG."
        ),
        status="answered",
        citations=[],
        route=strategy_id,
        confidence=0.0,
        evidence_coverage=0.0,
        trace_steps=[],
        trace=[],
        path_evidence=[],
        seeds=[],
        warnings=[f"Strategy {strategy_id} is planned — returned stub answer"],
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        fallback_strategy="auralynq_rag",
        fallback_reason="strategy_not_implemented",
    )


class LightRAGLocalStrategy(RAGStrategy):
    id = "lightrag_local"
    name = "LightRAG-style Local"
    description = "Entity-centric retrieval using local entity neighborhoods. (LightRAG, Guo et al. 2024)"
    status = "planned"
    required_features = ["graph_index"]
    supports_graph = True
    expected_latency = "medium"
    best_for = "Entity-specific questions requiring neighborhood context"
    limitations = "Not yet implemented — requires dedicated graph index build"

    def is_available(self) -> tuple[bool, str]:
        return False, "LightRAG-style local retrieval is planned. Not yet implemented."

    def run(self, query: str, **kwargs: Any) -> StrategyResult:
        return _not_implemented(self.id, self.name, query)


class LightRAGGlobalStrategy(RAGStrategy):
    id = "lightrag_global"
    name = "LightRAG-style Global"
    description = "Community-level summary retrieval for broad synthesis. (LightRAG, Guo et al. 2024)"
    status = "planned"
    required_features = ["graph_index", "community_summaries"]
    supports_graph = True
    expected_latency = "slow"
    best_for = "High-level synthesis and theme discovery questions"
    limitations = "Not yet implemented — requires community summary build step"

    def is_available(self) -> tuple[bool, str]:
        return False, "LightRAG-style global retrieval is planned. Not yet implemented."

    def run(self, query: str, **kwargs: Any) -> StrategyResult:
        return _not_implemented(self.id, self.name, query)


class LightRAGHybridStrategy(RAGStrategy):
    id = "lightrag_hybrid"
    name = "LightRAG-style Hybrid/Mix"
    description = "Combines local entity + global community retrieval. (LightRAG, Guo et al. 2024)"
    status = "planned"
    required_features = ["graph_index", "community_summaries"]
    supports_graph = True
    expected_latency = "slow"
    best_for = "Complex questions requiring both entity detail and global context"
    limitations = "Not yet implemented"

    def is_available(self) -> tuple[bool, str]:
        return False, "LightRAG-style hybrid retrieval is planned. Not yet implemented."

    def run(self, query: str, **kwargs: Any) -> StrategyResult:
        return _not_implemented(self.id, self.name, query)


class RAPTORStrategy(RAGStrategy):
    id = "raptor"
    name = "RAPTOR-style Hierarchical"
    description = "Hierarchical summary tree retrieval. (Sarthi et al. 2024)"
    status = "planned"
    required_features = ["hierarchical_index"]
    supports_graph = False
    expected_latency = "medium"
    best_for = "Multi-document synthesis and broad coverage questions"
    limitations = "Requires hierarchical index build — not yet implemented"

    def is_available(self) -> tuple[bool, str]:
        return False, "RAPTOR-style hierarchical retrieval is planned. Requires hierarchical index build."

    def run(self, query: str, **kwargs: Any) -> StrategyResult:
        return _not_implemented(self.id, self.name, query)


class SelfRAGStrategy(RAGStrategy):
    id = "self_rag"
    name = "Self-RAG-style Reflective"
    description = "LLM decides when to retrieve and critiques its own output. (Asai et al. 2023)"
    status = "planned"
    required_features = []
    supports_abstention = True
    expected_latency = "slow"
    best_for = "Questions where retrieval necessity is uncertain"
    limitations = "Full Self-RAG requires fine-tuned model with reflection tokens — using approximation"

    def is_available(self) -> tuple[bool, str]:
        return False, "Self-RAG reflection tokens require a fine-tuned model. Not yet implemented."

    def run(self, query: str, **kwargs: Any) -> StrategyResult:
        return _not_implemented(self.id, self.name, query)


class CRAGStrategy(RAGStrategy):
    id = "crag"
    name = "CRAG-style Corrective"
    description = "Evaluates retrieval quality; triggers web fallback if insufficient. (Yan et al. 2024)"
    status = "planned"
    required_features = ["web_search"]
    supports_web = True
    supports_abstention = True
    expected_latency = "slow"
    best_for = "Questions where corpus coverage may be incomplete"
    limitations = "Requires web search to be enabled"

    def is_available(self) -> tuple[bool, str]:
        try:
            from auralynq.config import get_settings

            s = get_settings()
            if getattr(s, "web_search_enabled", False):
                return False, "CRAG requires web search — not yet fully implemented"
            return False, "CRAG requires web search. Set AURALYNQ_WEB_SEARCH=true."
        except Exception:
            return False, "CRAG requires web search — not yet implemented."

    def run(self, query: str, **kwargs: Any) -> StrategyResult:
        return _not_implemented(self.id, self.name, query)


class AdaptiveRAGStrategy(RAGStrategy):
    id = "adaptive"
    name = "Adaptive-RAG"
    description = "Classifies query complexity; routes to cheapest sufficient strategy. (Jeong et al. 2024)"
    status = "planned"
    required_features = []
    supports_abstention = True
    expected_latency = "fast"
    best_for = "Mixed workloads — auto-selects simple/complex path"
    limitations = "Complexity classifier not yet trained on domain data"

    def is_available(self) -> tuple[bool, str]:
        return False, "Adaptive-RAG complexity classifier is planned. Not yet implemented."

    def run(self, query: str, **kwargs: Any) -> StrategyResult:
        return _not_implemented(self.id, self.name, query)


class KeywordBM25Strategy(RAGStrategy):
    id = "keyword_bm25"
    name = "Keyword / BM25"
    description = "Pure lexical retrieval using BM25 scoring. Best for exact-match queries."
    status = "available"
    required_features = []
    supports_graph = False
    supports_rerank = False
    expected_latency = "fast"
    best_for = "Exact phrase matching, technical terms, named entities"
    limitations = "No semantic understanding; misses paraphrase variants"

    def run(self, query: str, final_k: int = 6, use_cache: bool = True, route_hint: str = "", **kwargs: Any) -> StrategyResult:
        from auralynq.agent.runner import answer_question

        res = answer_question(query, final_k=final_k, use_cache=use_cache, route_hint="keyword")
        d = res.to_dict()
        return StrategyResult(
            answer=d.get("answer", ""),
            status=d.get("status", "answered"),
            citations=d.get("citations", []),
            route="keyword_bm25",
            confidence=d.get("confidence", 0.0),
            evidence_coverage=d.get("evidence_coverage", 0.0),
            trace_steps=d.get("trace_steps", []),
            trace=d.get("trace", []),
            path_evidence=[],
            seeds=d.get("seeds", []),
            warnings=["Strategy: keyword only — no semantic matching"],
            strategy_id=self.id,
            strategy_name=self.name,
            elapsed_ms=d.get("elapsed_ms", 0.0),
            iterations=d.get("iterations", 0),
            detected_entities=d.get("detected_entities", []),
            suggested_questions=d.get("suggested_questions", []),
            cached=d.get("cached", False),
        )
