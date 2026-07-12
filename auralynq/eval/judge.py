"""LLM-as-judge for the eval harness — upgrades the deterministic lexical proxies
(citation attribution, faithfulness, answer correctness) to NLI-style judgement
by a real model.

Opt-in (``auralynq eval --judge``): uses the configured LLM (local Ollama or a
Hugging Face Inference Provider). Every call is best-effort — an unparseable or
failed judgement returns ``None`` so callers can fall back to the lexical scorer
rather than crash or silently score 0.
"""

from __future__ import annotations

import re

_SENT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def _sentences(text: str) -> list[str]:
    return [p.strip() for p in _SENT_RE.split(text or "") if p.strip()]


class LLMJudge:
    """Wraps an LLM with yes/no eval prompts. Deterministic (temperature 0)."""

    def __init__(self, llm) -> None:
        self._llm = llm

    @property
    def name(self) -> str:
        return getattr(self._llm, "name", "llm")

    def _yesno(self, prompt: str) -> bool | None:
        try:
            out = self._llm.generate(prompt, max_tokens=4, temperature=0.0).strip().lower()
        except Exception:
            return None
        if out.startswith("yes") or out.startswith("true"):
            return True
        if out.startswith("no") or out.startswith("false"):
            return False
        return None

    def supports(self, claim: str, evidence: str) -> bool | None:
        """Does the evidence entail the claim? (citation attribution / faithfulness)"""
        if not claim.strip() or not evidence.strip():
            return None
        return self._yesno(
            "You are a strict fact-checker. Does the EVIDENCE support the CLAIM? "
            "Answer only 'yes' or 'no'.\n"
            f"CLAIM: {claim}\nEVIDENCE: {evidence[:1200]}"
        )

    def correct(self, question: str, prediction: str, reference: str) -> bool | None:
        """Is the predicted answer correct w.r.t. the reference? (calibration label)"""
        if not prediction.strip():
            return False
        if not reference.strip():
            return None
        return self._yesno(
            "Is the PREDICTED answer correct and consistent with the REFERENCE answer "
            "for the question? Minor wording differences are fine. Answer only 'yes' or 'no'.\n"
            f"QUESTION: {question}\nREFERENCE: {reference}\nPREDICTED: {prediction[:1200]}"
        )

    def faithfulness(self, answer: str, contexts: list[str]) -> float | None:
        """Fraction of answer sentences entailed by the retrieved context."""
        sents = _sentences(answer)
        if not sents:
            return None
        ctx = "\n".join(contexts)[:4000]
        judged = [self.supports(s, ctx) for s in sents]
        decided = [v for v in judged if v is not None]
        if not decided:
            return None
        return round(sum(1 for v in decided if v) / len(decided), 4)
