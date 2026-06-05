"""Fit a learned calibrator from a run's traces (Contribution C2).

Reads ``runs/<id>/traces/*.json``, builds (ESC feature vector, raw confidence,
correctness) tuples for the scored items, fits a :class:`LogisticCalibrator`, and
reports calibration metrics **before** (raw ESC confidence) vs **after** (learned)
so the improvement is auditable. The fitted calibrator is sklearn-free at
inference and is applied by the runner when ``abstention.mode == "calibrated"``
and a calibrator path is supplied.

Honesty: by default metrics are in-sample (small dev runs). Pass ``holdout`` to
split a test fraction; we label which mode was used in the report.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from auralynq.research.calibration import (
    LogisticCalibrator,
    aurc,
    brier_score,
    expected_calibration_error,
)
from auralynq.research.trace import ResearchTrace, load_traces

# Feature keys used for the learned calibrator (subset of ESC features that are
# populated by the runner; order is fixed for stable serialization).
CALIBRATION_FEATURES = [
    "top_k_retrieval_score",
    "retrieval_score_margin",
    "reranker_score",
    "citation_coverage",
    "graph_path_reliability",
    "source_agreement",
    "n_supporting_chunks",
]


def _rows_from_traces(
    traces: list[ResearchTrace],
) -> tuple[list[dict[str, Any]], list[float], list[int]]:
    feats: list[dict[str, Any]] = []
    raw_conf: list[float] = []
    correct: list[int] = []
    for t in traces:
        es = t.evidence_sufficiency or {}
        c = t.metrics.get("correct")
        if c is None:
            continue  # no gold label -> excluded from calibration
        feats.append(es.get("features", {}))
        raw_conf.append(float(es.get("confidence", 0.0)))
        correct.append(int(c))
    return feats, raw_conf, correct


def _metrics(conf: list[float], correct: list[int]) -> dict[str, float]:
    return {
        "ece": round(expected_calibration_error(conf, correct), 4),
        "brier": round(brier_score(conf, correct), 4),
        "aurc": round(aurc(conf, correct), 4),
        "n": len(conf),
    }


def fit_calibrator_from_run(
    run_dir: str | Path, holdout: float = 0.0
) -> tuple[LogisticCalibrator | None, dict[str, Any]]:
    """Fit a logistic calibrator from a run. Returns (calibrator, report).

    ``holdout`` in (0,1) reserves the last fraction of items for out-of-sample
    metrics; otherwise metrics are in-sample (labeled as such).
    """
    traces = load_traces(run_dir)
    feats, raw_conf, correct = _rows_from_traces(traces)
    n = len(correct)
    if n < 5 or len(set(correct)) < 2:
        return None, {
            "status": "insufficient_data",
            "n_scored": n,
            "note": "need >=5 scored items spanning both classes to fit a calibrator",
        }

    if 0.0 < holdout < 1.0:
        cut = max(1, int(n * (1 - holdout)))
        tr_idx, te_idx = list(range(cut)), list(range(cut, n))
        eval_mode = f"holdout({holdout})"
    else:
        tr_idx = te_idx = list(range(n))
        eval_mode = "in-sample"

    cal = LogisticCalibrator(feature_keys=CALIBRATION_FEATURES)
    cal.fit([feats[i] for i in tr_idx], [correct[i] for i in tr_idx])

    cal_conf = [cal.predict_one(raw_conf[i], feats[i]) for i in range(n)]
    before = _metrics([raw_conf[i] for i in te_idx], [correct[i] for i in te_idx])
    after = _metrics([cal_conf[i] for i in te_idx], [correct[i] for i in te_idx])

    report = {
        "status": "ok",
        "eval_mode": eval_mode,
        "n_scored": n,
        "feature_keys": CALIBRATION_FEATURES,
        "before_raw": before,
        "after_learned": after,
        "delta": {
            "ece": round(after["ece"] - before["ece"], 4),
            "brier": round(after["brier"] - before["brier"], 4),
            "aurc": round(after["aurc"] - before["aurc"], 4),
        },
        "note": (
            "Negative deltas = improvement. In-sample numbers are optimistic; use "
            "holdout or a separate dev run before citing in the paper."
        ),
    }
    return cal, report


def fit_and_save(run_dir: str | Path, output: str | Path, holdout: float = 0.0) -> dict[str, Any]:
    cal, report = fit_calibrator_from_run(run_dir, holdout=holdout)
    if cal is not None:
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(cal.to_json(), indent=2), encoding="utf-8")
        report["calibrator_path"] = str(out)
    return report
