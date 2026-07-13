"""SelfCheckGPT-style self-consistency signal.

Intuition (arXiv 2303.08896): an answer grounded in the evidence is *stable* when
the model is resampled; a hallucinated one drifts. We resample the answer a few
times at higher temperature and measure how much the original agrees with the
samples. High agreement → consistent → lower hallucination risk.

Agreement is lexical (content-token Jaccard) so the signal is fully offline and
$0 — no judge model required — matching the calibrated-confidence node's other
signals. When a real judge LLM is configured, a stronger NLI-based agreement can
be layered behind the same ``consistency_score`` interface later.
"""

from __future__ import annotations

from auralynq.llm.base import LLM, Context
from auralynq.utils import tokenize


def _content_tokens(text: str) -> set[str]:
    return {t for t in tokenize(text or "") if len(t) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def consistency_score(main_answer: str, samples: list[str]) -> float:
    """Mean agreement between the main answer and its resamples, in [0, 1].

    1.0 = every resample restates the same content (stable); 0.0 = no overlap
    (the answer changes each time — a hallucination signature). Empty sample set
    is treated as fully consistent (nothing contradicts the answer).
    """
    if not samples:
        return 1.0
    m = _content_tokens(main_answer)
    scores = [_jaccard(m, _content_tokens(s)) for s in samples]
    return round(sum(scores) / len(scores), 3)


def sample_answers(
    llm: LLM,
    question: str,
    contexts: list[Context],
    n: int,
    *,
    temperature: float = 0.7,
    max_tokens: int = 512,
) -> list[str]:
    """Resample the answer ``n`` times at ``temperature`` over the same evidence."""
    out: list[str] = []
    for _ in range(max(n, 0)):
        try:
            out.append(
                llm.answer(question, contexts, temperature=temperature, max_tokens=max_tokens)
            )
        except Exception:  # pragma: no cover - provider hiccup; skip this sample
            continue
    return out
