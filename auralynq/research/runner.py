"""Reproducible experiment runner.

Executes a dataset through the Auralynq pipeline under one :class:`ResearchConfig`,
applies the Evidence Sufficiency Controller for abstention, runs offline judges,
computes per-example + aggregate metrics, and writes a fully-provenanced run
directory:

    runs/<run_id>/
      provenance.json      # git hash, config, seed, hardware, redacted env
      config.snapshot.yaml # frozen config
      results.json         # per-example records
      metrics.json         # aggregate metrics
      traces/<qid>.json    # one ResearchTrace per question

Real components are used (retrievers, optional agent, LLM). The non-agentic modes
retrieve directly (real scores); ``full_agentic`` uses the production agent. No
fabricated numbers; abstention is honest.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from auralynq.research import metrics as M
from auralynq.research.calibration import get_calibrator
from auralynq.research.config import ResearchConfig, load_config
from auralynq.research.datasets import get_adapter
from auralynq.research.datasets.base import NormalizedExample
from auralynq.research.evaluators import JudgeInput, offline_judges
from auralynq.research.evidence_sufficiency import (
    EvidenceSufficiencyController,
    extract_features,
)
from auralynq.research.provenance import build_provenance
from auralynq.research.trace import ResearchTrace, write_trace

ABSTAIN_MSG = "I don't have enough evidence in the indexed sources to answer that."


# --------------------------------------------------------------- retrieval ----
def _retrieve(config: ResearchConfig):
    """Build the retriever implied by the config (real components)."""
    from auralynq.retrieval.hybrid.retriever import HybridRetriever
    from auralynq.retrieval.naive import NaiveRetriever
    from auralynq.vectorstore.factory import get_store

    store = get_store()
    if config.use_graph:
        from auralynq.pipeline import load_graph
        from auralynq.retrieval.pathrag.retriever import PathRAGRetriever

        hybrid = HybridRetriever(store=store)
        return PathRAGRetriever(load_graph(), store=store, embedder=hybrid.embedder)
    if config.retrieval.mode == "dense":
        return NaiveRetriever(store=store)
    return HybridRetriever(store=store)


def _cite(sc) -> dict[str, Any]:
    c = sc.chunk.citation()
    return {
        "source": str(c.get("source", "")),
        "locator": str(c.get("locator", "")),
        "score": round(float(getattr(sc, "score", 0.0) or 0.0), 4),
        "text": sc.chunk.text[:280],
    }


def _reranker_score(sc) -> float | None:
    comp = getattr(sc, "components", {}) or {}
    for key in ("rerank", "reranker", "cross_encoder"):
        if key in comp:
            return float(comp[key])
    return None


# --------------------------------------------------------------- execution ----
def execute_example(
    config: ResearchConfig,
    ex: NormalizedExample,
    controller: EvidenceSufficiencyController,
    calibrator: Any = None,
) -> ResearchTrace:
    t0 = time.perf_counter()
    final_k = config.retrieval.final_k

    route = "retrieval-only"
    route_conf = 0.0
    path_evidence: list[dict[str, Any]] = []
    warnings: list[str] = []
    agent_trace: list[dict[str, Any]] = []
    agent_abstained = False
    provider_error = False

    # --- gather contexts + real retrieval scores
    chunks = _retrieve(config).retrieve(ex.question, config.retrieval.top_k).chunks[:final_k]
    contexts = [c.chunk.text for c in chunks]
    retrieval_scores = [float(getattr(c, "score", 0.0) or 0.0) for c in chunks]
    reranker_scores = [s for s in (_reranker_score(c) for c in chunks) if s is not None]
    citations = [_cite(c) for c in chunks]

    # --- generation
    if config.retrieval.mode == "full_agentic":
        try:
            from auralynq.agent.runner import answer_question

            ar = answer_question(ex.question, final_k=final_k, use_cache=False)
            answer = ar.answer
            route, route_conf = ar.route, ar.route_confidence
            path_evidence = ar.path_evidence
            warnings = ar.warnings
            agent_trace = ar.trace
            agent_abstained = ar.status == "insufficient_evidence"
            if ar.contexts:
                contexts = ar.contexts
            if ar.citations:
                citations = ar.citations
        except Exception as exc:
            provider_error = True
            warnings.append(f"agent error: {exc}")
            answer = _extractive_answer(ex.question, contexts)
    else:
        answer = _generate(ex.question, citations)

    # --- evidence sufficiency / abstention
    cov = M.citation_metrics_proxy(answer, citations, contexts)["citation_coverage"]
    path_reliabilities = [float(p.get("reliability", 0.0)) for p in path_evidence]
    signals = {
        "retrieval_scores": retrieval_scores,
        "reranker_scores": reranker_scores,
        "n_supporting_chunks": len(contexts),
        "citation_coverage": cov,
        "graph_path_reliabilities": path_reliabilities,
        "source_agreement": _source_agreement(citations),
        "answer_len": len(answer.split()),
        "evidence_len": sum(len(c.split()) for c in contexts),
        "trace_warnings": len(warnings),
        "provider_fallback_used": any("fallback" in str(w).lower() for w in warnings),
        "language_mismatch": (ex.language not in ("en", "")) and bool(answer),
    }
    decision = controller.decide(extract_features(signals))

    # Learned calibration: in calibrated mode, map ESC features -> calibrated
    # confidence and use it for the abstain decision + reporting. Raw confidence is
    # preserved for auditing. Identity calibrator (default) is a no-op.
    raw_confidence = decision.confidence
    es_dict = decision.to_dict()
    if calibrator is not None and config.abstention.mode == "calibrated":
        cal_conf = round(float(calibrator.predict_one(raw_confidence, decision.features)), 4)
        es_dict["raw_confidence"] = raw_confidence
        es_dict["confidence"] = cal_conf
        es_dict["calibrator"] = getattr(calibrator, "name", "identity")
        eff_confidence = cal_conf
    else:
        eff_confidence = raw_confidence

    abstain = _resolve_abstention(config, decision, signals, agent_abstained, eff_confidence)
    final_answer = ABSTAIN_MSG if abstain else answer

    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    # --- per-example metrics
    ground = M.groundedness_proxy(final_answer, contexts) if not abstain else 0.0
    correct = _is_correct(ex, final_answer, abstain)
    per_metrics = {
        "groundedness_proxy": ground,
        "unsupported_claim_rate_proxy": round(1 - ground, 4) if not abstain else 0.0,
        "token_f1": round(M.token_f1(final_answer, ex.gold_answer), 4),
        "exact_match": M.exact_match(final_answer, ex.gold_answer),
        "answer_relevance_proxy": M.answer_relevance_proxy(ex.question, final_answer),
        "correct": correct,
        "confidence": eff_confidence,
    }
    per_metrics.update(M.citation_metrics_proxy(final_answer, citations, contexts))

    # --- judges (offline, deterministic)
    jin = JudgeInput(
        question=ex.question,
        answer=final_answer,
        contexts=contexts,
        citations=citations,
        gold_answer=ex.gold_answer,
        gold_contexts=ex.gold_contexts,
        abstained=abstain,
        requires_abstention=ex.requires_abstention,
        language=ex.language,
    )
    judges = [j.judge(jin).to_dict() for j in offline_judges()]

    return ResearchTrace(
        question_id=ex.question_id,
        question=ex.question,
        route=route,
        route_confidence=route_conf,
        detected_entities=[],
        retrieval_mode=config.retrieval.mode,
        retrieval_scores=retrieval_scores,
        reranker_scores=reranker_scores,
        n_contexts=len(contexts),
        graph_paths=path_evidence,
        evidence_sufficiency=es_dict,
        abstained=abstain,
        answer=final_answer,
        citations=citations,
        contexts=contexts,
        judges=judges,
        metrics=per_metrics,
        provider=config.llm.provider,
        model=config.llm.model,
        elapsed_ms=round(elapsed_ms, 2),
        warnings=warnings,
        provider_error=provider_error,
        trace=agent_trace,
    )


def _generate(question: str, citations: list[dict[str, Any]]) -> str:
    """Generate an answer from retrieved contexts via the configured LLM."""
    from auralynq.llm.base import Context
    from auralynq.llm.factory import get_llm

    ctxs = [
        Context(
            marker=i + 1,
            text=c.get("text", ""),
            source=c.get("source", ""),
            locator=c.get("locator", ""),
        )
        for i, c in enumerate(citations)
    ]
    if not ctxs:
        return ABSTAIN_MSG
    try:
        llm = get_llm()
        return llm.answer(question, ctxs).strip()
    except Exception:
        return _extractive_answer(question, [c.get("text", "") for c in citations])


def _extractive_answer(question: str, contexts: list[str]) -> str:
    return contexts[0][:280] if contexts else ABSTAIN_MSG


def _source_agreement(citations: list[dict[str, Any]]) -> float:
    """Crude agreement proxy: 1 - unique_sources/total (more overlap = agreement)."""
    srcs = [c.get("source", "") for c in citations if c.get("source")]
    if len(srcs) < 2:
        return 0.5
    return round(1 - (len(set(srcs)) / len(srcs)), 4)


def _resolve_abstention(
    config: ResearchConfig,
    decision,
    signals: dict[str, Any],
    agent_abstained: bool,
    eff_confidence: float | None = None,
) -> bool:
    mode = config.abstention.mode
    if mode == "none":
        return False
    if mode == "threshold":
        # Simple baseline: abstain on low normalized top-score or missing citations.
        top_score = decision.features.get("top_k_retrieval_score", 0.0)
        low_score = top_score < config.abstention.threshold
        no_citation = (
            config.abstention.citation_required and signals.get("citation_coverage", 0) <= 0
        )
        return bool(low_score or no_citation)
    if mode == "calibrated" and eff_confidence is not None:
        # Hard ESC constraints (no supporting chunks / required-but-absent
        # citations) still apply; otherwise abstain on the *calibrated* confidence.
        no_support = int(signals.get("n_supporting_chunks", 0)) < 1
        no_citation = (
            config.abstention.citation_required and signals.get("citation_coverage", 0) <= 0
        )
        low_conf = eff_confidence < config.abstention.threshold
        return bool(no_support or no_citation or low_conf or agent_abstained)
    # heuristic / judge use the ESC decision; agent abstention OR'd in.
    return bool(decision.abstain or agent_abstained)


def _is_correct(ex: NormalizedExample, answer: str, abstain: bool) -> int | None:
    """Honest correctness: abstain-correct on unanswerable; F1>=0.5 otherwise.

    Returns None when there is no gold answer to check (excluded from accuracy).
    """
    if ex.requires_abstention:
        return int(abstain)
    if abstain:
        return 0
    if not ex.gold_answer:
        return None
    return int(M.token_f1(answer, ex.gold_answer) >= 0.5)


# ------------------------------------------------------------------- run -------
def _aggregate(traces: list[ResearchTrace]) -> dict[str, Any]:
    confidences = [t.evidence_sufficiency.get("confidence", 0.0) for t in traces]
    # only items with a defined correctness contribute to accuracy/calibration
    idx = [i for i, t in enumerate(traces) if t.metrics.get("correct") is not None]
    correct = [int(traces[i].metrics["correct"]) for i in idx]
    conf = [confidences[i] for i in idx]
    abst = [int(traces[i].abstained) for i in idx]

    ground = [t.metrics.get("groundedness_proxy", 0.0) for t in traces]
    f1 = [t.metrics.get("token_f1", 0.0) for t in traces]
    cite_prec = [t.metrics.get("citation_precision_proxy", 0.0) for t in traces]
    cov = [t.metrics.get("citation_coverage", 0.0) for t in traces]

    out: dict[str, Any] = {
        "n": len(traces),
        "n_scored": len(idx),
        "abstention_rate": round(sum(t.abstained for t in traces) / max(1, len(traces)), 4),
        "mean_token_f1": round(sum(f1) / max(1, len(f1)), 4),
        "grounded_answer_rate": M.grounded_answer_rate(ground),
        "mean_groundedness_proxy": round(sum(ground) / max(1, len(ground)), 4),
        "mean_citation_precision_proxy": round(sum(cite_prec) / max(1, len(cite_prec)), 4),
        "mean_citation_coverage": round(sum(cov) / max(1, len(cov)), 4),
    }
    if conf:
        out["abstention_calibration"] = M.abstention_metrics(conf, correct, abst)
    out["trace"] = M.trace_metrics([t.to_dict() for t in traces])
    return out


def run(
    config_path: str | Path,
    dataset: str,
    output_dir: str | Path,
    limit: int | None = None,
    use_mini: bool = False,
    extra_env: dict[str, str] | None = None,
    calibrator_path: str | Path | None = None,
) -> dict[str, Any]:
    config = load_config(config_path)
    config.apply()
    if extra_env:
        # Applied AFTER config so callers (e.g. the offline smoke) can force
        # deterministic providers regardless of the config's `auto` values.
        import os

        from auralynq.config import reload_settings

        os.environ.update(extra_env)
        reload_settings()

    started = datetime.now(UTC)
    t0 = time.perf_counter()

    adapter = get_adapter("mini") if (use_mini or dataset == "mini") else get_adapter(dataset)
    examples = adapter.load(limit=limit)

    # Calibrator: learned one if a path is supplied, else identity (no-op).
    if calibrator_path is not None:
        from auralynq.research.calibration import load_calibrator

        calibrator = load_calibrator(calibrator_path)
    else:
        calibrator = get_calibrator("identity")
    controller = EvidenceSufficiencyController(
        abstain_threshold=config.abstention.threshold,
        citation_required=config.abstention.citation_required,
    )

    run_dir = Path(output_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    traces: list[ResearchTrace] = []
    for ex in examples:
        tr = execute_example(config, ex, controller, calibrator=calibrator)
        write_trace(tr, run_dir)
        traces.append(tr)

    aggregate = _aggregate(traces)
    duration = time.perf_counter() - t0

    config.to_yaml(run_dir / "config.snapshot.yaml")
    provenance = build_provenance(
        config=config.model_dump(mode="json"),
        dataset=dataset,
        n_examples=len(examples),
        started_iso=started.isoformat(),
        duration_s=duration,
        extra={
            "dataset_source": adapter.source,
            "dataset_license": adapter.license,
            "calibrator": getattr(calibrator, "name", "identity"),
            "calibrator_path": str(calibrator_path) if calibrator_path else None,
        },
    )
    (run_dir / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    (run_dir / "results.json").write_text(
        json.dumps([t.to_dict() for t in traces], indent=2), encoding="utf-8"
    )
    (run_dir / "metrics.json").write_text(json.dumps(aggregate, indent=2), encoding="utf-8")
    return {"run_dir": str(run_dir), "n": len(traces), "metrics": aggregate}


def evaluate_run(run_dir: str | Path) -> dict[str, Any]:
    """Recompute aggregate metrics from a run's traces."""
    from auralynq.research.trace import load_traces

    traces = load_traces(run_dir)
    agg = _aggregate(traces)
    (Path(run_dir) / "metrics.json").write_text(json.dumps(agg, indent=2), encoding="utf-8")
    return agg
