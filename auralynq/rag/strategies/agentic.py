"""Agentic multi-hop RAG — decompose → retrieve → judge sufficiency → re-retrieve."""

from __future__ import annotations

import time
from typing import Any

from auralynq.rag.strategies.base import RAGStrategy, StrategyResult


class AgenticLoopStrategy(RAGStrategy):
    id = "agentic"
    name = "Agentic Loop"
    description = (
        "Multi-hop retrieve-then-reason: decomposes the question into sub-questions, "
        "retrieves per hop while accumulating evidence, and uses an LLM to judge "
        "sufficiency and propose follow-up queries (Self-RAG / IRCoT)."
    )
    status = "available"
    required_features: list[str] = []
    supports_streaming = True
    supports_graph = True
    supports_rerank = True
    supports_web = False
    supports_abstention = True
    expected_latency = "slow"  # several retrieval + LLM hops
    best_for = "Multi-hop / comparative questions that a single retrieval can't answer"
    limitations = "Slower (multiple LLM + retrieval hops); needs a real LLM for decomposition"

    def is_available(self) -> tuple[bool, str]:
        # Degrades to ~single-shot on the offline extractive LLM, so always usable.
        return True, ""

    def run(
        self,
        query: str,
        final_k: int = 6,
        use_cache: bool = True,  # ignored: the agentic loop never uses the shared cache
        route_hint: str = "",
        **kwargs: Any,
    ) -> StrategyResult:
        from auralynq.agent.runner import answer_question

        t0 = time.perf_counter()
        res = answer_question(query, final_k=final_k, route_hint=route_hint, agentic=True)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        d = res.to_dict()
        return StrategyResult(
            answer=d.get("answer", ""),
            status=d.get("status", "answered"),
            citations=d.get("citations", []),
            route=d.get("route", "fast"),
            confidence=d.get("confidence", 0.0),
            evidence_coverage=d.get("evidence_coverage", 0.0),
            trace_steps=d.get("trace_steps", []),
            trace=d.get("trace", []),
            path_evidence=d.get("path_evidence", []),
            seeds=d.get("seeds", []),
            warnings=d.get("warnings", []),
            strategy_id=self.id,
            strategy_name=self.name,
            elapsed_ms=d.get("elapsed_ms", elapsed_ms),
            iterations=d.get("iterations", 0),
            detected_entities=d.get("detected_entities", []),
            suggested_questions=d.get("suggested_questions", []),
            cached=False,
            route_confidence=d.get("route_confidence", 1.0),
            route_rationale=d.get("route_rationale", ""),
            confidence_signals=d.get("confidence_signals", {}),
        )
