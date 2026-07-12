"""Evaluation regression gate — turn the trust metrics into a pass/fail check.

Extracts the key quality + trust metrics from an eval report and compares each
against a threshold (floor for good-is-high metrics, ceiling for good-is-low
error metrics). Used by ``auralynq eval --gate`` to fail CI on a regression.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# metric -> (comparison, threshold). ">=" is a floor, "<=" is a ceiling.
DEFAULT_THRESHOLDS: dict[str, tuple[str, float]] = {
    "agentic_recall_at_k": (">=", 0.5),
    "faithfulness": (">=", 0.5),
    "citation_precision": (">=", 0.5),
    "attribution_rate": (">=", 0.5),
    "unsupported_claim_rate": ("<=", 0.5),
    "ece": ("<=", 0.2),
}


@dataclass
class GateCheck:
    metric: str
    value: float | None
    op: str
    threshold: float
    passed: bool


def extract_metrics(report: dict[str, Any]) -> dict[str, float]:
    """Pull the gateable metrics out of a run_eval report (missing → skipped)."""
    ag = report.get("agentic", {}) or {}
    out: dict[str, float] = {}
    retr = ag.get("retrieval", {})
    if "recall_at_k" in retr:
        out["agentic_recall_at_k"] = retr["recall_at_k"]
    ragas = ag.get("ragas", {})
    if "faithfulness" in ragas:
        out["faithfulness"] = ragas["faithfulness"]
    cit = ag.get("citation", {})
    for key in ("citation_precision", "attribution_rate", "unsupported_claim_rate"):
        if key in cit:
            out[key] = cit[key]
    cal = ag.get("calibration", {})
    if "ece" in cal:
        out["ece"] = cal["ece"]
    return out


def eval_gate(
    report: dict[str, Any], thresholds: dict[str, tuple[str, float]] | None = None
) -> dict[str, Any]:
    """Return ``{passed, checks, failures}``. A metric absent from the report is
    skipped (not failed), so partial reports don't spuriously fail."""
    thresholds = thresholds or DEFAULT_THRESHOLDS
    metrics = extract_metrics(report)
    checks: list[GateCheck] = []
    for metric, (op, thr) in thresholds.items():
        if metric not in metrics:
            continue
        val = metrics[metric]
        ok = val >= thr if op == ">=" else val <= thr
        checks.append(GateCheck(metric, round(float(val), 4), op, thr, ok))
    failures = [c for c in checks if not c.passed]
    return {
        "passed": not failures,
        "checks": [c.__dict__ for c in checks],
        "failures": [c.__dict__ for c in failures],
    }
