"""Calibration + selective-prediction math — Contribution C2.

Two parts:
  1. **Calibrators** that map a raw confidence (or feature vector) to a calibrated
     P(correct): Identity, Temperature scaling (Guo et al. 2017, arXiv:1706.04599),
     and an optional learned Logistic calibrator (sklearn, lazily imported).
  2. **Metrics** for calibrated abstention: ECE, Abstain-ECE, Brier, the
     coverage-risk curve and its area (AURC).

Pure-Python/NumPy so it runs offline at $0; sklearn only needed for the learned
calibrator. These functions are re-exported by ``metrics.py``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------- metrics ---


def brier_score(confidences: list[float], correct: list[int]) -> float:
    """Mean squared error between confidence and correctness (lower better)."""
    if not confidences:
        return 0.0
    return sum((c - y) ** 2 for c, y in zip(confidences, correct, strict=True)) / len(confidences)


def expected_calibration_error(
    confidences: list[float], correct: list[int], n_bins: int = 10
) -> float:
    """ECE with equal-width bins (Guo et al. 2017)."""
    if not confidences:
        return 0.0
    n = len(confidences)
    ece = 0.0
    for b in range(n_bins):
        lo, hi = b / n_bins, (b + 1) / n_bins
        idx = [i for i, c in enumerate(confidences) if (c > lo or (b == 0 and c >= lo)) and c <= hi]
        if not idx:
            continue
        avg_conf = sum(confidences[i] for i in idx) / len(idx)
        acc = sum(correct[i] for i in idx) / len(idx)
        ece += (len(idx) / n) * abs(avg_conf - acc)
    return ece


def reliability_bins(
    confidences: list[float], correct: list[int], n_bins: int = 10
) -> list[dict[str, float]]:
    """Per-bin (confidence, accuracy, count) for reliability diagrams."""
    out: list[dict[str, float]] = []
    n = len(confidences)
    for b in range(n_bins):
        lo, hi = b / n_bins, (b + 1) / n_bins
        idx = [i for i, c in enumerate(confidences) if (c > lo or (b == 0 and c >= lo)) and c <= hi]
        if not idx:
            out.append({"bin_lo": lo, "bin_hi": hi, "conf": 0.0, "acc": 0.0, "count": 0})
            continue
        out.append(
            {
                "bin_lo": lo,
                "bin_hi": hi,
                "conf": sum(confidences[i] for i in idx) / len(idx),
                "acc": sum(correct[i] for i in idx) / len(idx),
                "count": len(idx),
                "frac": len(idx) / n,
            }
        )
    return out


def abstain_ece(
    confidences: list[float], correct: list[int], abstained: list[int], n_bins: int = 10
) -> float:
    """Abstain-ECE: ECE computed only over *answered* items (abstention survey)."""
    pairs = [(c, y) for c, y, a in zip(confidences, correct, abstained, strict=True) if not a]
    if not pairs:
        return 0.0
    cs = [c for c, _ in pairs]
    ys = [y for _, y in pairs]
    return expected_calibration_error(cs, ys, n_bins=n_bins)


def coverage_risk_curve(confidences: list[float], correct: list[int]) -> list[dict[str, float]]:
    """Risk vs. coverage: sort by confidence desc, accumulate error rate.

    At coverage k/n we answer the top-k most-confident items; risk = error rate
    on that answered subset. Used to compute AURC.
    """
    if not confidences:
        return []
    order = sorted(range(len(confidences)), key=lambda i: confidences[i], reverse=True)
    n = len(order)
    curve: list[dict[str, float]] = []
    errors = 0
    for k, i in enumerate(order, start=1):
        errors += 1 - correct[i]
        curve.append({"coverage": k / n, "risk": errors / k, "threshold": confidences[i]})
    return curve


def aurc(confidences: list[float], correct: list[int]) -> float:
    """Area under the risk-coverage curve (lower is better)."""
    curve = coverage_risk_curve(confidences, correct)
    if not curve:
        return 0.0
    return sum(p["risk"] for p in curve) / len(curve)


def selective_accuracy(correct: list[int], abstained: list[int]) -> dict[str, float]:
    """Accuracy on the answered subset + coverage."""
    answered = [c for c, a in zip(correct, abstained, strict=True) if not a]
    n = len(correct)
    return {
        "coverage": (len(answered) / n) if n else 0.0,
        "selective_accuracy": (sum(answered) / len(answered)) if answered else 0.0,
        "abstention_rate": (1 - len(answered) / n) if n else 0.0,
    }


# ------------------------------------------------------------------ calibrators ---


class Calibrator:
    """Base calibrator: maps a raw score (or feature dict) to P(correct)."""

    name = "identity"

    def predict_one(self, raw_confidence: float, features: dict[str, Any] | None = None) -> float:
        return max(0.0, min(1.0, raw_confidence))

    def fit(self, X: list[Any], y: list[int]) -> Calibrator:
        return self

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name}

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_json(), indent=2), encoding="utf-8")


class IdentityCalibrator(Calibrator):
    name = "identity"


class TemperatureScaler(Calibrator):
    """Single-parameter temperature scaling on the logit of the raw confidence."""

    name = "temperature"

    def __init__(self, temperature: float = 1.0) -> None:
        self.temperature = temperature

    @staticmethod
    def _logit(p: float) -> float:
        p = min(max(p, 1e-6), 1 - 1e-6)
        return math.log(p / (1 - p))

    def predict_one(self, raw_confidence: float, features: dict[str, Any] | None = None) -> float:
        z = self._logit(raw_confidence) / max(self.temperature, 1e-3)
        return 1.0 / (1.0 + math.exp(-z))

    def fit(self, X: list[float], y: list[int]) -> TemperatureScaler:
        """Grid-search temperature minimizing ECE (small, dependency-free)."""
        best_t, best_ece = 1.0, float("inf")
        for t in [round(0.2 + 0.1 * i, 2) for i in range(0, 49)]:  # 0.2..5.0
            self.temperature = t
            cal = [self.predict_one(p) for p in X]
            e = expected_calibration_error(cal, y)
            if e < best_ece:
                best_ece, best_t = e, t
        self.temperature = best_t
        return self

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "temperature": self.temperature}


class LogisticCalibrator(Calibrator):
    """Learned calibrator over ESC features (optional; needs scikit-learn).

    Falls back to identity behavior until ``fit`` is called. Feature order is
    fixed by ``feature_keys`` so serialization is stable.
    """

    name = "logistic"

    def __init__(self, feature_keys: list[str] | None = None) -> None:
        self.feature_keys = feature_keys or []
        self._model = None

    def _vec(self, features: dict[str, Any]) -> list[float]:
        return [float(features.get(k, 0.0) or 0.0) for k in self.feature_keys]

    def fit(self, X: list[dict[str, Any]], y: list[int]) -> LogisticCalibrator:
        from sklearn.linear_model import LogisticRegression  # lazy

        if not self.feature_keys and X:
            self.feature_keys = sorted(X[0].keys())
        mat = [self._vec(x) for x in X]
        self._model = LogisticRegression(max_iter=1000).fit(mat, y)
        return self

    def predict_one(self, raw_confidence: float, features: dict[str, Any] | None = None) -> float:
        if self._model is None or not features:
            return max(0.0, min(1.0, raw_confidence))
        proba = self._model.predict_proba([self._vec(features)])[0][1]
        return float(proba)

    def to_json(self) -> dict[str, Any]:
        info: dict[str, Any] = {"name": self.name, "feature_keys": self.feature_keys}
        if self._model is not None:
            info["coef"] = self._model.coef_.tolist()
            info["intercept"] = self._model.intercept_.tolist()
        return info


def get_calibrator(kind: str = "identity", **kwargs: Any) -> Calibrator:
    return {
        "identity": IdentityCalibrator,
        "temperature": TemperatureScaler,
        "logistic": LogisticCalibrator,
    }.get(kind, IdentityCalibrator)(**kwargs)
