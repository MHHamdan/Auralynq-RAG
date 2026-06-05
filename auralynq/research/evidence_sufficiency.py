"""Evidence Sufficiency Controller (ESC) — Contribution C1.

Decides, from *transparent* retrieval/graph/citation features, whether the
retrieved evidence is sufficient to answer or whether Auralynq should abstain.
This is a **research module first**: the v0 scorer is an interpretable weighted
sum so every decision is explainable; a learned calibrator (see
``calibration.py``) can later replace the score→confidence mapping without
changing the feature contract.

Honesty: the controller is allowed to *abstain*; it must never be tuned to make
the system answer when evidence is weak. Thresholds are configurable.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SufficiencyFeatures(BaseModel):
    """All features the controller may use. All optional; missing → neutral.

    Values are normalized to roughly [0, 1] where higher = more support, except
    where noted (``contradiction_signal``, ``language_mismatch``,
    ``provider_fallback_used`` are *risk* signals where higher = worse).
    """

    top_k_retrieval_score: float = 0.0  # best retrieval score (normalized)
    retrieval_score_margin: float = 0.0  # gap between top-1 and top-2
    reranker_score: float = 0.0  # best reranker score if reranking ran
    n_supporting_chunks: int = 0  # contexts above relevance floor
    citation_coverage: float = 0.0  # frac of answer sentences with a citation
    graph_path_support_count: int = 0  # # PathRAG paths backing the answer
    graph_path_reliability: float = 0.0  # mean path reliability if available
    source_agreement: float = 0.0  # agreement across retrieved snippets
    contradiction_signal: float = 0.0  # RISK: detected contradiction (0..1)
    answer_evidence_ratio: float = 1.0  # answer length vs evidence coverage
    model_self_confidence: float = 0.0  # model-reported confidence if available
    trace_warnings: int = 0  # # warnings emitted in the trace
    provider_fallback_used: bool = False  # RISK: a fallback provider was used
    language_mismatch: bool = False  # RISK: answer/query language mismatch
    extraction_quality: float = 1.0  # parse/extraction quality (0..1)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump()


class SufficiencyDecision(BaseModel):
    evidence_sufficient: bool
    abstain: bool
    confidence: float  # 0..1 calibrated support for the answer
    hallucination_risk: float  # 0..1, higher = riskier
    calibration_bucket: str  # low | medium | high
    reasons: list[str] = Field(default_factory=list)
    features: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


# Transparent feature weights (sum of positive weights = 1.0). Documented so the
# decision is auditable; a learned calibrator can override the score→confidence map.
_WEIGHTS: dict[str, float] = {
    "top_k_retrieval_score": 0.22,
    "retrieval_score_margin": 0.08,
    "reranker_score": 0.18,
    "citation_coverage": 0.20,
    "graph_path_reliability": 0.10,
    "source_agreement": 0.12,
    "extraction_quality": 0.10,
}
# Risk penalties subtracted from the support score.
_PENALTIES: dict[str, float] = {
    "contradiction_signal": 0.25,
    "language_mismatch": 0.20,
    "provider_fallback_used": 0.08,
    "trace_warning_unit": 0.04,  # per warning, capped
}


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


class EvidenceSufficiencyController:
    """Maps :class:`SufficiencyFeatures` to a :class:`SufficiencyDecision`."""

    def __init__(
        self,
        abstain_threshold: float = 0.5,
        citation_required: bool = True,
        min_supporting_chunks: int = 1,
    ) -> None:
        self.abstain_threshold = abstain_threshold
        self.citation_required = citation_required
        self.min_supporting_chunks = min_supporting_chunks

    def support_score(self, f: SufficiencyFeatures) -> float:
        score = 0.0
        score += _WEIGHTS["top_k_retrieval_score"] * _clip01(f.top_k_retrieval_score)
        score += _WEIGHTS["retrieval_score_margin"] * _clip01(f.retrieval_score_margin)
        score += _WEIGHTS["reranker_score"] * _clip01(f.reranker_score)
        score += _WEIGHTS["citation_coverage"] * _clip01(f.citation_coverage)
        score += _WEIGHTS["graph_path_reliability"] * _clip01(f.graph_path_reliability)
        score += _WEIGHTS["source_agreement"] * _clip01(f.source_agreement)
        score += _WEIGHTS["extraction_quality"] * _clip01(f.extraction_quality)

        # Risk penalties
        score -= _PENALTIES["contradiction_signal"] * _clip01(f.contradiction_signal)
        if f.language_mismatch:
            score -= _PENALTIES["language_mismatch"]
        if f.provider_fallback_used:
            score -= _PENALTIES["provider_fallback_used"]
        score -= min(0.16, _PENALTIES["trace_warning_unit"] * max(0, f.trace_warnings))

        # Over-long answers relative to evidence are penalized (likely padding).
        if f.answer_evidence_ratio > 2.0:
            score -= 0.05
        return _clip01(score)

    def decide(self, f: SufficiencyFeatures) -> SufficiencyDecision:
        confidence = self.support_score(f)
        reasons: list[str] = []

        hard_abstain = False
        if f.n_supporting_chunks < self.min_supporting_chunks:
            hard_abstain = True
            reasons.append(
                f"only {f.n_supporting_chunks} supporting chunk(s) (< {self.min_supporting_chunks})"
            )
        if self.citation_required and f.citation_coverage <= 0.0:
            hard_abstain = True
            reasons.append("citations required but answer has no citation coverage")
        if f.contradiction_signal >= 0.5:
            reasons.append("strong contradiction signal across sources")
        if f.language_mismatch:
            reasons.append("answer/query language mismatch")
        if f.provider_fallback_used:
            reasons.append("a fallback provider was used")

        abstain = hard_abstain or confidence < self.abstain_threshold
        if abstain and not reasons:
            reasons.append(
                f"confidence {confidence:.2f} below abstain threshold {self.abstain_threshold:.2f}"
            )
        if not abstain:
            reasons.append(f"sufficient evidence (confidence {confidence:.2f})")

        # Hallucination risk: low confidence + active risk signals.
        risk = _clip01(
            (1.0 - confidence) * 0.7
            + f.contradiction_signal * 0.2
            + (0.1 if f.provider_fallback_used else 0.0)
        )
        bucket = "high" if confidence >= 0.7 else "medium" if confidence >= 0.4 else "low"

        return SufficiencyDecision(
            evidence_sufficient=not abstain,
            abstain=abstain,
            confidence=round(confidence, 4),
            hallucination_risk=round(risk, 4),
            calibration_bucket=bucket,
            reasons=reasons,
            features=f.as_dict(),
        )


# ----------------------------------------------------------------- extraction ---
def _normalize_scores(scores: list[float]) -> list[float]:
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    if hi - lo < 1e-9:
        return [1.0 for _ in scores]
    return [(s - lo) / (hi - lo) for s in scores]


def extract_features(signals: dict[str, Any]) -> SufficiencyFeatures:
    """Build :class:`SufficiencyFeatures` from a runner-populated signal dict.

    Recognized keys (all optional):
      retrieval_scores: list[float], reranker_scores: list[float],
      n_supporting_chunks: int, citation_coverage: float,
      graph_path_reliabilities: list[float], source_agreement: float,
      contradiction_signal: float, answer_len: int, evidence_len: int,
      model_self_confidence: float, trace_warnings: int,
      provider_fallback_used: bool, language_mismatch: bool,
      extraction_quality: float.
    """
    rscores = list(signals.get("retrieval_scores") or [])
    norm = _normalize_scores(rscores)
    top = norm[0] if norm else 0.0
    margin = (norm[0] - norm[1]) if len(norm) >= 2 else (norm[0] if norm else 0.0)
    rr = list(signals.get("reranker_scores") or [])
    rr_norm = _normalize_scores(rr)
    paths = list(signals.get("graph_path_reliabilities") or [])
    answer_len = float(signals.get("answer_len", 0) or 0)
    evidence_len = float(signals.get("evidence_len", 0) or 0)
    ratio = (answer_len / evidence_len) if evidence_len > 0 else 1.0

    return SufficiencyFeatures(
        top_k_retrieval_score=top,
        retrieval_score_margin=max(0.0, margin),
        reranker_score=(max(rr_norm) if rr_norm else 0.0),
        n_supporting_chunks=int(signals.get("n_supporting_chunks", len(rscores))),
        citation_coverage=float(signals.get("citation_coverage", 0.0)),
        graph_path_support_count=len(paths),
        graph_path_reliability=(sum(paths) / len(paths)) if paths else 0.0,
        source_agreement=float(signals.get("source_agreement", 0.0)),
        contradiction_signal=float(signals.get("contradiction_signal", 0.0)),
        answer_evidence_ratio=ratio,
        model_self_confidence=float(signals.get("model_self_confidence", 0.0)),
        trace_warnings=int(signals.get("trace_warnings", 0)),
        provider_fallback_used=bool(signals.get("provider_fallback_used", False)),
        language_mismatch=bool(signals.get("language_mismatch", False)),
        extraction_quality=float(signals.get("extraction_quality", 1.0)),
    )
