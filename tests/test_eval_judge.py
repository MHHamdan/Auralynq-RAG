"""LLM-as-judge for the eval harness — yes/no parsing, faithfulness, and its use
in citation attribution (with lexical fallback when undecided). No real model."""

from __future__ import annotations

from auralynq.eval.citation_eval import citation_scores
from auralynq.eval.judge import LLMJudge


class _FnLLM:
    """Deterministic fake LLM: generate(prompt) -> fn(prompt)."""

    name = "fn"

    def __init__(self, fn):
        self.fn = fn
        self.calls = 0

    def generate(self, prompt, **kw):
        self.calls += 1
        return self.fn(prompt)


def test_yesno_parsing():
    assert LLMJudge(_FnLLM(lambda p: "Yes, it does.")).supports("a", "b") is True
    assert LLMJudge(_FnLLM(lambda p: "no")).supports("a", "b") is False
    assert LLMJudge(_FnLLM(lambda p: "unsure")).supports("a", "b") is None  # unparseable
    # empty claim/evidence → None (undecided, not a call)
    assert LLMJudge(_FnLLM(lambda p: "yes")).supports("", "b") is None


def test_generate_raises_is_non_fatal():
    def boom(_):
        raise RuntimeError("model down")

    assert LLMJudge(_FnLLM(boom)).supports("a", "b") is None


def test_correct_and_faithfulness():
    j = LLMJudge(_FnLLM(lambda p: "yes"))
    assert j.correct("q?", "Paris", "Paris") is True
    assert j.correct("q?", "", "Paris") is False  # empty prediction is wrong, no call

    answers = iter(["yes", "no"])  # 2 sentences → one supported, one not
    jf = LLMJudge(_FnLLM(lambda p: next(answers)))
    assert jf.faithfulness("Claim one. Claim two.", ["ctx"]) == 0.5


def test_citation_scores_use_judge():
    # judge says 'yes' only when the evidence mentions Ericsson
    def verdict(prompt):
        evidence = prompt.split("EVIDENCE:")[-1]
        return "yes" if "Ericsson" in evidence else "no"

    j = LLMJudge(_FnLLM(verdict))
    good = {"text": "Ericsson filed FRAND patents with standards bodies", "source": "e.pdf"}
    spurious = {"text": "The weather was sunny all weekend", "source": "w.pdf"}

    s = citation_scores(
        [{"answer": "Ericsson filed FRAND patents.", "citations": [good, spurious]}], judge=j
    )
    assert s.method == "llm_judge"
    assert s.citation_precision == 0.5  # good cited chunk backs the answer, spurious does not
    assert s.attribution_rate == 1.0  # the single claim is entailed by the good citation


def test_citation_judge_falls_back_to_lexical_when_undecided():
    # judge always undecided → falls back to the lexical scorer, not zero
    j = LLMJudge(_FnLLM(lambda p: "hmm"))
    good = {
        "text": "Ericsson filed fair reasonable FRAND patent licensing terms",
        "source": "e.pdf",
    }
    s = citation_scores(
        [{"answer": "Ericsson filed FRAND patent licensing terms.", "citations": [good]}], judge=j
    )
    assert s.method == "llm_judge"
    assert s.citation_precision == 1.0  # lexical fallback still credits the overlapping citation
