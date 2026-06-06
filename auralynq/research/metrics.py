"""Research evaluation metrics.

Grouped to match ``docs/research/evaluation-metrics.md``: retrieval, generation /
citation, abstention / calibration, trace / observability, efficiency.

Honesty conventions:
  * Heuristic surrogates (no judge / no gold) carry a ``_proxy`` suffix so they
    are never confused with judge or human scores.
  * Calibration math is imported from :mod:`auralynq.research.calibration`.
  * Retrieval math reuses :mod:`auralynq.eval.retrieval_metrics`.
"""

from __future__ import annotations

import re
import statistics
from typing import Any

from auralynq.eval.retrieval_metrics import aggregate as _retrieval_aggregate
from auralynq.research.calibration import (
    abstain_ece,
    aurc,
    brier_score,
    coverage_risk_curve,
    expected_calibration_error,
    reliability_bins,
    selective_accuracy,
)

_WORD = re.compile(r"\w+")


def _tokens(text: str) -> list[str]:
    return _WORD.findall((text or "").lower())


def _token_set(text: str) -> set[str]:
    return set(_tokens(text))


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [p for p in parts if p.strip()]


# ----------------------------------------------------------------- retrieval ---
def retrieval_metrics(cases: list[tuple[set[str], list[str]]], k: int = 10) -> dict[str, float]:
    s = _retrieval_aggregate(cases, k=k)
    return {
        "recall_at_k": s.recall_at_k,
        "precision_at_k": s.precision_at_k,
        "ndcg_at_k": s.ndcg_at_k,
        "mrr": s.mrr,
        "n": s.n,
        "k": s.k,
    }


def context_precision_recall_proxy(
    retrieved_contexts: list[str], gold_contexts: list[str]
) -> dict[str, float]:
    """Token-overlap proxy for context precision/recall (no gold spans needed)."""
    if not retrieved_contexts:
        return {"context_precision_proxy": 0.0, "context_recall_proxy": 0.0}
    gold_tok = set().union(*[_token_set(g) for g in gold_contexts]) if gold_contexts else set()
    if not gold_tok:
        return {"context_precision_proxy": 0.0, "context_recall_proxy": 0.0}
    hit = sum(1 for c in retrieved_contexts if _token_set(c) & gold_tok)
    retrieved_tok = set().union(*[_token_set(c) for c in retrieved_contexts])
    return {
        "context_precision_proxy": round(hit / len(retrieved_contexts), 4),
        "context_recall_proxy": round(len(gold_tok & retrieved_tok) / len(gold_tok), 4),
    }


# -------------------------------------------------------- generation / answer ---
def exact_match(pred: str, gold: str) -> int:
    return int(_tokens(pred) == _tokens(gold) and bool(gold))


def token_f1(pred: str, gold: str) -> float:
    p, g = _tokens(pred), _tokens(gold)
    if not p or not g:
        return 0.0
    common = 0
    gold_counts: dict[str, int] = {}
    for t in g:
        gold_counts[t] = gold_counts.get(t, 0) + 1
    for t in p:
        if gold_counts.get(t, 0) > 0:
            common += 1
            gold_counts[t] -= 1
    if common == 0:
        return 0.0
    prec, rec = common / len(p), common / len(g)
    return 2 * prec * rec / (prec + rec)


def answer_relevance_proxy(question: str, answer: str) -> float:
    """Token-overlap proxy (deterministic, offline). Use a judge for real scoring."""
    q, a = _token_set(question), _token_set(answer)
    if not q or not a:
        return 0.0
    return round(len(q & a) / len(q), 4)


def groundedness_proxy(answer: str, contexts: list[str]) -> float:
    """Fraction of answer sentences with token support in the contexts (proxy)."""
    sents = _sentences(answer)
    if not sents:
        return 0.0
    ctx_tok = set().union(*[_token_set(c) for c in contexts]) if contexts else set()
    if not ctx_tok:
        return 0.0
    supported = 0
    for s in sents:
        st = _token_set(s)
        if not st:
            continue
        overlap = len(st & ctx_tok) / len(st)
        if overlap >= 0.5:
            supported += 1
    return round(supported / len(sents), 4)


def unsupported_claim_rate_proxy(answer: str, contexts: list[str]) -> float:
    return round(1.0 - groundedness_proxy(answer, contexts), 4)


def citation_metrics_proxy(
    answer: str, citations: list[dict[str, Any]], contexts: list[str]
) -> dict[str, float]:
    """ALCE-style proxy: coverage (does answer cite?), precision (do cited
    contexts overlap the answer?), recall (frac of answer sentences cited)."""
    sents = _sentences(answer)
    n_sents = max(1, len(sents))
    n_cites = len(citations)
    coverage = 1.0 if n_cites > 0 and answer.strip() else 0.0
    # precision proxy: cited sources whose text overlaps the answer
    ans_tok = _token_set(answer)
    cited_texts = [c.get("text", "") for c in citations if c.get("text")]
    if not cited_texts:
        cited_texts = contexts[:n_cites]
    if cited_texts and ans_tok:
        good = sum(1 for t in cited_texts if len(_token_set(t) & ans_tok) >= 3)
        precision = good / len(cited_texts)
    else:
        precision = 0.0
    recall = min(1.0, n_cites / n_sents)
    return {
        "citation_coverage": round(coverage, 4),
        "citation_precision_proxy": round(precision, 4),
        "citation_recall_proxy": round(recall, 4),
    }


# ----------------------------------------------------- abstention / calibration ---
def abstention_metrics(
    confidences: list[float],
    correct: list[int],
    abstained: list[int],
) -> dict[str, Any]:
    """Full selective-prediction + calibration suite over a run."""
    sel = selective_accuracy(correct, abstained)
    # false-answer: answered but wrong; false-abstention: abstained but would be right
    n = max(1, len(correct))
    false_answer = sum(1 for c, a in zip(correct, abstained, strict=True) if not a and c == 0)
    false_abstention = sum(1 for c, a in zip(correct, abstained, strict=True) if a and c == 1)
    answered_idx = [i for i, a in enumerate(abstained) if not a]
    return {
        **sel,
        "aurc": round(aurc(confidences, correct), 4),
        "ece": round(expected_calibration_error(confidences, correct), 4),
        "abstain_ece": round(abstain_ece(confidences, correct, abstained), 4),
        "brier": round(brier_score(confidences, correct), 4),
        "false_answer_rate": round(false_answer / n, 4),
        "false_abstention_rate": round(false_abstention / n, 4),
        "answered_accuracy": (
            round(sum(correct[i] for i in answered_idx) / len(answered_idx), 4)
            if answered_idx
            else 0.0
        ),
        "reliability_bins": reliability_bins(confidences, correct),
        "coverage_risk_curve": coverage_risk_curve(confidences, correct),
        "n": len(correct),
    }


def grounded_answer_rate(groundedness_scores: list[float], threshold: float = 0.5) -> float:
    if not groundedness_scores:
        return 0.0
    return round(
        sum(1 for g in groundedness_scores if g >= threshold) / len(groundedness_scores), 4
    )


# -------------------------------------------------------- trace / efficiency ---
def trace_metrics(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Latency percentiles, trace completeness, fallback + failure distribution."""
    if not traces:
        return {"n": 0}
    lat = [float(t.get("elapsed_ms", 0.0) or 0.0) for t in traces]
    expected_steps = {
        "route",
        "retrieve",
        "fuse",
        "synthesizer",
        "self_check",
        "validate_citations",
    }
    completeness, fallbacks, errors = [], 0, 0
    failure_steps: dict[str, int] = {}
    for t in traces:
        steps = {s.get("name", "") for s in t.get("trace", [])}
        present = sum(1 for e in expected_steps if any(e in s for s in steps))
        completeness.append(present / len(expected_steps))
        warnings = t.get("warnings", []) or []
        if any("fallback" in str(w).lower() for w in warnings):
            fallbacks += 1
        if t.get("provider_error"):
            errors += 1
        for w in warnings:
            failure_steps[str(w)[:60]] = failure_steps.get(str(w)[:60], 0) + 1
    return {
        "n": len(traces),
        "latency_p50_ms": round(statistics.median(lat), 2),
        "latency_p95_ms": round(_percentile(lat, 95), 2),
        "latency_mean_ms": round(statistics.fmean(lat), 2),
        "trace_completeness": round(statistics.fmean(completeness), 4),
        "fallback_frequency": round(fallbacks / len(traces), 4),
        "provider_error_rate": round(errors / len(traces), 4),
        "failure_step_distribution": dict(
            sorted(failure_steps.items(), key=lambda kv: -kv[1])[:10]
        ),
    }


def efficiency_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Tokens, throughput, latency. Cost only if per-1k pricing is provided."""
    if not records:
        return {"n": 0}
    tin = [float(r.get("tokens_in", 0) or 0) for r in records]
    tout = [float(r.get("tokens_out", 0) or 0) for r in records]
    ttft = [float(r["ttft_ms"]) for r in records if r.get("ttft_ms")]
    lat_s = [float(r.get("elapsed_ms", 0) or 0) / 1000.0 for r in records]
    total_out = sum(tout)
    total_time = sum(lat_s) or 1e-9
    out = {
        "n": len(records),
        "tokens_in_total": int(sum(tin)),
        "tokens_out_total": int(total_out),
        "throughput_tokens_per_s": round(total_out / total_time, 2),
        "ttft_p50_ms": round(statistics.median(ttft), 2) if ttft else None,
    }
    return out


def cost_estimate(
    tokens_in: int, tokens_out: int, price_in_per_1k: float, price_out_per_1k: float
) -> float:
    """API cost estimate — only meaningful when pricing is explicitly supplied."""
    return round(tokens_in / 1000 * price_in_per_1k + tokens_out / 1000 * price_out_per_1k, 6)


def _percentile(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = (len(s) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)
