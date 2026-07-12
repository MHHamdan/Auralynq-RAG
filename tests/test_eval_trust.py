"""Trust metrics — citation attribution, confidence calibration (ECE), and the
regression gate. Deterministic, no model/network."""

from __future__ import annotations

from auralynq.eval.calibration import answer_correct, calibration_scores
from auralynq.eval.citation_eval import citation_scores
from auralynq.eval.gate import eval_gate


# ── calibration ─────────────────────────────────────────────────────────────


def test_calibration_perfect_is_zero_ece():
    # bin [0.9,1.0): confidence 0.9, 9/10 correct → acc 0.9 == conf 0.9 → ECE 0
    pairs = [(0.9, True)] * 9 + [(0.9, False)]
    s = calibration_scores(pairs)
    assert s.accuracy == 0.9
    assert s.ece == 0.0


def test_calibration_overconfident_has_max_ece():
    # confidence 1.0 everywhere, but only half correct → gap 0.5 in the top bin
    pairs = [(1.0, True)] * 5 + [(1.0, False)] * 5
    s = calibration_scores(pairs)
    assert s.accuracy == 0.5
    assert s.avg_confidence == 1.0
    assert s.ece == 0.5
    assert s.mce == 0.5
    assert s.brier == 0.5  # mean((1-1)^2 x5, (1-0)^2 x5) = 0.5


def test_calibration_empty():
    s = calibration_scores([])
    assert s.n == 0 and s.ece == 0.0


def test_answer_correct():
    assert answer_correct("The capital is Paris.", "Paris") is True
    assert answer_correct("Ericsson filed FRAND patent licensing terms", "FRAND patent licensing") is True
    assert answer_correct("The weather is sunny", "Paris") is False
    assert answer_correct("", "Paris") is False


# ── citation attribution ────────────────────────────────────────────────────


def test_citation_precision_penalizes_spurious():
    good = {"text": "Ericsson filed fair reasonable FRAND patent licensing terms with standards bodies", "source": "ericsson.pdf"}
    spurious = {"text": "The weather in Paris was sunny throughout the summer holidays", "source": "weather.pdf"}
    answer = "Ericsson filed FRAND patent licensing terms."

    both = citation_scores([{"answer": answer, "citations": [good, spurious]}])
    only_good = citation_scores([{"answer": answer, "citations": [good]}])
    assert only_good.citation_precision == 1.0
    # the spurious citation drops precision (it doesn't back the answer)
    assert both.citation_precision < only_good.citation_precision
    assert both.avg_citations == 2.0


def test_attribution_and_unsupported_rate():
    # one supported claim + one unsupported claim
    cites = [{"text": "Ericsson filed fair reasonable FRAND patent licensing terms", "source": "e.pdf"}]
    answer = "Ericsson filed FRAND patent licensing terms. The moon orbits earth every month."
    s = citation_scores([{"answer": answer, "citations": cites}])
    assert 0.0 < s.attribution_rate < 1.0  # first claim supported, second not
    assert round(s.attribution_rate + s.unsupported_claim_rate, 4) == 1.0


def test_citation_empty():
    s = citation_scores([])
    assert s.n == 0 and s.citation_precision == 0.0


# ── gate ────────────────────────────────────────────────────────────────────


def _report(cit_prec, ece, faith=0.8, recall=0.8, attr=0.8, unsup=0.2):
    return {
        "agentic": {
            "retrieval": {"recall_at_k": recall},
            "ragas": {"faithfulness": faith},
            "citation": {"citation_precision": cit_prec, "attribution_rate": attr, "unsupported_claim_rate": unsup},
            "calibration": {"ece": ece},
        }
    }


def test_gate_passes_when_healthy():
    g = eval_gate(_report(cit_prec=0.9, ece=0.05))
    assert g["passed"] is True and g["failures"] == []


def test_gate_fails_on_low_citation_precision_and_high_ece():
    g = eval_gate(_report(cit_prec=0.3, ece=0.4))
    assert g["passed"] is False
    failed = {f["metric"] for f in g["failures"]}
    assert "citation_precision" in failed
    assert "ece" in failed


def test_gate_skips_absent_metrics():
    # a report missing citation/calibration must not spuriously fail
    g = eval_gate({"agentic": {"retrieval": {"recall_at_k": 0.9}, "ragas": {"faithfulness": 0.9}}})
    assert g["passed"] is True
    metrics = {c["metric"] for c in g["checks"]}
    assert "citation_precision" not in metrics
