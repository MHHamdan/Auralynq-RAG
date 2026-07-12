"""Confidence calibration metrics — turns "calibrated confidence" from a claim
into a measured property.

Given (confidence, correct) pairs over a labelled golden set, we compute the
**Expected Calibration Error** (ECE), Maximum Calibration Error (MCE), Brier
score, and a reliability table (per-bin accuracy vs. mean confidence). A
well-calibrated system has ECE≈0: when it says 0.8, it is right ~80% of the
time. This is the honest test behind Auralynq's confidence signals.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from auralynq.utils import tokenize

_STOP = {"the", "a", "an", "is", "are", "was", "were", "of", "to", "in", "on",
         "and", "or", "that", "this", "it", "as", "for", "with", "by", "at", "be"}

#: A prediction is "correct" if it covers this fraction of the ground-truth's
#: content tokens (or contains the ground-truth string). Deterministic, offline.
CORRECT_TAU = 0.5


def _content_tokens(text: str) -> set[str]:
    return {t for t in tokenize(text or "") if t not in _STOP and len(t) > 2}


def answer_correct(prediction: str, ground_truth: str, *, tau: float = CORRECT_TAU) -> bool:
    """Lexical correctness: the prediction covers the ground truth. Used to label
    calibration pairs without a human or paid judge."""
    gt = (ground_truth or "").lower().strip()
    pred = (prediction or "").lower().strip()
    if not gt:
        return bool(pred)
    if gt in pred:
        return True
    gt_tok = _content_tokens(ground_truth)
    if not gt_tok:
        return gt in pred
    return len(_content_tokens(prediction) & gt_tok) / len(gt_tok) >= tau


@dataclass
class CalibrationScores:
    ece: float
    mce: float
    brier: float
    accuracy: float
    avg_confidence: float
    n: int
    bins: list[dict]


def calibration_scores(pairs: list[tuple[float, bool]], *, n_bins: int = 10) -> CalibrationScores:
    """Compute ECE/MCE/Brier + a reliability table from (confidence, correct) pairs."""
    pairs = [(max(0.0, min(1.0, float(c))), bool(y)) for c, y in pairs]
    n = len(pairs)
    if n == 0:
        return CalibrationScores(0.0, 0.0, 0.0, 0.0, 0.0, 0, [])

    # equal-width bins over [0, 1]
    bins: list[dict] = []
    ece = 0.0
    mce = 0.0
    for i in range(n_bins):
        lo = i / n_bins
        hi = (i + 1) / n_bins
        # last bin is closed on the right so confidence==1.0 lands somewhere
        in_bin = [
            (c, y)
            for c, y in pairs
            if (c >= lo and c < hi) or (i == n_bins - 1 and c == 1.0)
        ]
        cnt = len(in_bin)
        if cnt == 0:
            bins.append({"lo": round(lo, 2), "hi": round(hi, 2), "count": 0, "accuracy": None, "confidence": None})
            continue
        acc = sum(1 for _, y in in_bin if y) / cnt
        conf = sum(c for c, _ in in_bin) / cnt
        gap = abs(acc - conf)
        ece += (cnt / n) * gap
        mce = max(mce, gap)
        bins.append(
            {"lo": round(lo, 2), "hi": round(hi, 2), "count": cnt, "accuracy": round(acc, 4), "confidence": round(conf, 4)}
        )

    brier = sum((c - (1.0 if y else 0.0)) ** 2 for c, y in pairs) / n
    accuracy = sum(1 for _, y in pairs if y) / n
    avg_conf = sum(c for c, _ in pairs) / n
    return CalibrationScores(
        ece=round(ece, 4),
        mce=round(mce, 4),
        brier=round(brier, 4),
        accuracy=round(accuracy, 4),
        avg_confidence=round(avg_conf, 4),
        n=n,
        bins=bins,
    )


def to_dict(scores: CalibrationScores) -> dict:
    return asdict(scores)
