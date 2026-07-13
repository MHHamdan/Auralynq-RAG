"""Self-consistency hallucination signal (Feature 06) — offline tests."""

from __future__ import annotations

import pytest
from auralynq.agent.runner import answer_question
from auralynq.agent.self_consistency import consistency_score, sample_answers
from auralynq.config import reload_settings
from auralynq.pipeline import build_index


# --------------------------------------------------------------- units ------
def test_consistency_score_identical_is_high():
    assert consistency_score("Paris is the capital", ["Paris is the capital"] * 3) == 1.0


def test_consistency_score_divergent_is_low():
    # Disjoint content tokens → no agreement under resampling (hallucination sig).
    score = consistency_score("alpha bravo charlie", ["xray yankee zulu", "delta echo foxtrot"])
    assert score == 0.0


def test_consistency_score_partial_between():
    score = consistency_score("paris capital france", ["paris capital spain"])
    assert 0.0 < score < 1.0


def test_consistency_score_empty_samples_is_one():
    assert consistency_score("anything", []) == 1.0


class _VaryLLM:
    name = "vary"

    def __init__(self, answers: list[str]) -> None:
        self._answers = list(answers)
        self._i = 0

    def answer(self, question, contexts, **kw) -> str:
        a = self._answers[self._i % len(self._answers)]
        self._i += 1
        return a


def test_sample_answers_count():
    llm = _VaryLLM(["a", "b", "c"])
    out = sample_answers(llm, "q", [], 3)
    assert out == ["a", "b", "c"]


# ---------------------------------------------------- node integration ------
@pytest.fixture
def indexed(corpus_dir):
    build_index(corpus_dir)
    from auralynq.agent import runner

    runner._CACHE.clear()
    return corpus_dir


def test_signal_absent_by_default(indexed):
    res = answer_question("What is the capital of France?")
    assert "s_consistency" not in res.confidence_signals


def test_signal_present_when_enabled(indexed, monkeypatch):
    monkeypatch.setenv("AURALYNQ_AGENT__SELF_CONSISTENCY_ENABLED", "1")
    monkeypatch.setenv("AURALYNQ_AGENT__SELF_CONSISTENCY_SAMPLES", "3")
    reload_settings()
    from auralynq.agent import runner

    runner._CACHE.clear()
    res = answer_question("What is the capital of France?")
    assert "s_consistency" in res.confidence_signals
    s = res.confidence_signals["s_consistency"]
    assert 0.0 <= s <= 1.0
    # Deterministic extractive LLM → resamples match the main answer → high.
    assert s == pytest.approx(1.0)
