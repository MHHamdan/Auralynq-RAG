"""Per-query research trace schema + serialization (Contribution C3).

One :class:`ResearchTrace` is written per benchmark question to
``runs/<run_id>/traces/<question_id>.json``. It captures the full observable
pipeline so trace features can later be correlated with hallucination risk.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ResearchTrace(BaseModel):
    question_id: str
    question: str
    # routing / intent
    route: str = ""
    route_confidence: float = 0.0
    intent: str = ""
    detected_entities: list[str] = Field(default_factory=list)
    # retrieval / graph / rerank
    retrieval_mode: str = ""
    retrieval_scores: list[float] = Field(default_factory=list)
    reranker_scores: list[float] = Field(default_factory=list)
    n_contexts: int = 0
    graph_paths: list[dict[str, Any]] = Field(default_factory=list)
    # sufficiency / abstention
    evidence_sufficiency: dict[str, Any] = Field(default_factory=dict)
    abstained: bool = False
    # generation
    answer: str = ""
    citations: list[dict[str, Any]] = Field(default_factory=list)
    contexts: list[str] = Field(default_factory=list)
    # evaluation
    judges: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    # operational
    provider: str = ""
    model: str = ""
    elapsed_ms: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    provider_error: bool = False
    # raw span timeline from the underlying agent trace (if any)
    trace: list[dict[str, Any]] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    def feature_row(self) -> dict[str, Any]:
        """Flat row for trace-feature → hallucination-risk analysis (RQ3)."""
        es = self.evidence_sufficiency or {}
        feats = es.get("features", {})
        return {
            "question_id": self.question_id,
            "route": self.route,
            "route_confidence": self.route_confidence,
            "retrieval_mode": self.retrieval_mode,
            "n_contexts": self.n_contexts,
            "top_retrieval_score": (max(self.retrieval_scores) if self.retrieval_scores else 0.0),
            "reranker_score": (max(self.reranker_scores) if self.reranker_scores else 0.0),
            "n_graph_paths": len(self.graph_paths),
            "citation_coverage": feats.get("citation_coverage", 0.0),
            "confidence": es.get("confidence", 0.0),
            "hallucination_risk": es.get("hallucination_risk", 0.0),
            "abstained": int(self.abstained),
            "provider_fallback_used": int(feats.get("provider_fallback_used", False)),
            "language_mismatch": int(feats.get("language_mismatch", False)),
            "n_warnings": len(self.warnings),
            "elapsed_ms": self.elapsed_ms,
            "groundedness_proxy": self.metrics.get("groundedness_proxy", 0.0),
            "correct": self.metrics.get("correct"),
        }


def write_trace(trace: ResearchTrace, run_dir: str | Path) -> Path:
    traces_dir = Path(run_dir) / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)
    safe_id = trace.question_id.replace("/", "_")
    path = traces_dir / f"{safe_id}.json"
    path.write_text(json.dumps(trace.to_dict(), indent=2), encoding="utf-8")
    return path


def load_traces(run_dir: str | Path) -> list[ResearchTrace]:
    traces_dir = Path(run_dir) / "traces"
    if not traces_dir.exists():
        return []
    out: list[ResearchTrace] = []
    for p in sorted(traces_dir.glob("*.json")):
        out.append(ResearchTrace.model_validate_json(p.read_text(encoding="utf-8")))
    return out
