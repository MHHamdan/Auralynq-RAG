#!/usr/bin/env python3
"""Trace analysis — which trace features predict hallucination risk? (RQ3 / C3).

Loads ResearchTraces from one or more run directories and reports:
  * correlation of each trace feature with answer correctness,
  * when graph expansion / reranking appears to help,
  * which configs are over/under-confident (calibration gap),
  * abstention's effect on the wrong-answer rate.

Pure-Python with an optional scikit-learn logistic model for feature importance.
Usage:
    python scripts/research/analyze_traces.py runs/smoke_* [--json out.json]
"""

from __future__ import annotations

import argparse
import glob
import json
import math
from pathlib import Path
from typing import Any

from auralynq.research.trace import load_traces


def _point_biserial(x: list[float], y: list[int]) -> float:
    """Correlation between a continuous feature x and a binary outcome y."""
    n = len(x)
    if n < 3 or len(set(y)) < 2:
        return 0.0
    mean_x = sum(x) / n
    sd = math.sqrt(sum((v - mean_x) ** 2 for v in x) / n)
    if sd < 1e-9:
        return 0.0
    ones = [x[i] for i in range(n) if y[i] == 1]
    zeros = [x[i] for i in range(n) if y[i] == 0]
    if not ones or not zeros:
        return 0.0
    m1, m0 = sum(ones) / len(ones), sum(zeros) / len(zeros)
    p, q = len(ones) / n, len(zeros) / n
    return ((m1 - m0) / sd) * math.sqrt(p * q)


def analyze(run_dirs: list[str]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for rd in run_dirs:
        for t in load_traces(rd):
            r = t.feature_row()
            r["run"] = Path(rd).name
            rows.append(r)

    scored = [r for r in rows if r.get("correct") is not None]
    feature_keys = [
        "top_retrieval_score",
        "reranker_score",
        "n_graph_paths",
        "citation_coverage",
        "confidence",
        "n_contexts",
        "n_warnings",
        "elapsed_ms",
        "groundedness_proxy",
    ]
    correlations = {}
    if scored:
        y = [int(r["correct"]) for r in scored]
        for k in feature_keys:
            x = [float(r.get(k, 0.0) or 0.0) for r in scored]
            correlations[k] = round(_point_biserial(x, y), 4)

    # over/under-confidence: mean confidence vs accuracy
    calib_gap = None
    if scored:
        mean_conf = sum(float(r["confidence"]) for r in scored) / len(scored)
        acc = sum(int(r["correct"]) for r in scored) / len(scored)
        calib_gap = round(mean_conf - acc, 4)  # >0 overconfident, <0 underconfident

    # abstention effect: wrong-answer rate among answered vs everything
    answered = [r for r in scored if not r["abstained"]]
    wrong_answered = sum(1 for r in answered if int(r["correct"]) == 0)
    abst_effect = {
        "answered": len(answered),
        "wrong_answered": wrong_answered,
        "wrong_answer_rate_answered": round(wrong_answered / max(1, len(answered)), 4),
        "abstention_rate": round(sum(1 for r in rows if r["abstained"]) / max(1, len(rows)), 4),
    }

    importance = _logistic_importance(scored, feature_keys)

    return {
        "n_traces": len(rows),
        "n_scored": len(scored),
        "feature_correlation_with_correct": dict(
            sorted(correlations.items(), key=lambda kv: -abs(kv[1]))
        ),
        "logistic_feature_importance": importance,
        "calibration_gap_mean_conf_minus_acc": calib_gap,
        "abstention_effect": abst_effect,
        "note": (
            "Correlations are descriptive on a small N (smoke). Treat as exploratory; "
            "the paper requires larger benchmark runs + CIs."
        ),
    }


def _logistic_importance(scored: list[dict[str, Any]], keys: list[str]) -> dict[str, float]:
    if len(scored) < 10 or len({int(r["correct"]) for r in scored}) < 2:
        return {"_skipped": "need >=10 scored traces with both classes"}
    try:
        from sklearn.linear_model import LogisticRegression
    except Exception:
        return {"_skipped": "scikit-learn not installed"}
    X = [[float(r.get(k, 0.0) or 0.0) for k in keys] for r in scored]
    y = [int(r["correct"]) for r in scored]
    model = LogisticRegression(max_iter=1000).fit(X, y)
    return {k: round(float(c), 4) for k, c in zip(keys, model.coef_[0], strict=True)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("runs", nargs="+", help="Run directories (globs ok).")
    ap.add_argument("--json", dest="json_out", default=None, help="Write report JSON here.")
    args = ap.parse_args()

    expanded: list[str] = []
    for r in args.runs:
        hits = sorted(glob.glob(r))
        expanded.extend(hits if hits else [r])
    expanded = [p for p in expanded if Path(p).is_dir()]

    report = analyze(expanded)
    text = json.dumps(report, indent=2)
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
