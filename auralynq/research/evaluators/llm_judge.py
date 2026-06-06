"""LLM-as-judge — OPTIONAL and explicitly NOT ground truth.

Uses the configured Auralynq LLM to rate whether the answer is supported by the
retrieved contexts. If no real provider is available (offline/extractive
fallback), it degrades to the heuristic judge and says so, so results are never
silently fabricated. Known judge biases (MT-Bench, arXiv:2306.05685) mean this is
reported alongside agreement metrics, never as the gold standard.
"""

from __future__ import annotations

import re

from auralynq.research.evaluators.base import BaseJudge, JudgeInput, Verdict
from auralynq.research.evaluators.heuristic_judge import HeuristicJudge

_RUBRIC = (
    "You are evaluating a document-grounded answer. Given the QUESTION, the "
    "retrieved CONTEXT, and the ANSWER, decide if the answer is fully supported "
    "by the context. Reply on the first line with exactly SUPPORTED or "
    "UNSUPPORTED, then a one-sentence reason. Do not use outside knowledge."
)


class LLMJudge(BaseJudge):
    name = "llm"
    dimension = "support"
    requires_llm = True

    def __init__(self, llm=None, max_context_chars: int = 4000) -> None:
        self._llm = llm
        self.max_context_chars = max_context_chars
        self._fallback = HeuristicJudge()

    def _get_llm(self):
        if self._llm is not None:
            return self._llm
        from auralynq.llm.factory import get_llm

        self._llm = get_llm()
        return self._llm

    def _real_provider(self, llm) -> bool:
        # The offline extractive fallback is deterministic but not a judge.
        return getattr(llm, "name", "extractive") not in ("extractive", "base", "")

    def judge(self, inp: JudgeInput) -> Verdict:
        if inp.abstained:
            return Verdict(
                judge=self.name,
                dimension=self.dimension,
                label="abstained",
                rationale="system abstained; nothing to judge",
            )
        try:
            llm = self._get_llm()
        except Exception as exc:
            v = self._fallback.judge(inp)
            v.judge = self.name
            v.rationale = f"LLM unavailable ({exc}); fell back to heuristic: {v.rationale}"
            return v

        if not self._real_provider(llm):
            v = self._fallback.judge(inp)
            v.judge = self.name
            v.rationale = (
                f"no real LLM provider (got '{getattr(llm, 'name', '?')}'); "
                f"fell back to heuristic: {v.rationale}"
            )
            return v

        ctx = "\n".join(f"[{i + 1}] {c}" for i, c in enumerate(inp.contexts))[
            : self.max_context_chars
        ]
        prompt = f"QUESTION: {inp.question}\n\nCONTEXT:\n{ctx}\n\nANSWER: {inp.answer}\n\nVerdict:"
        try:
            out = llm.generate(prompt, system=_RUBRIC, temperature=0.0, max_tokens=120)
        except Exception as exc:
            v = self._fallback.judge(inp)
            v.judge = self.name
            v.rationale = f"LLM call failed ({exc}); heuristic: {v.rationale}"
            return v

        first = (out or "").strip().splitlines()[0] if out else ""
        supported = bool(re.search(r"\bSUPPORTED\b", first, re.I)) and not re.search(
            r"\bUNSUPPORTED\b", first, re.I
        )
        return Verdict(
            judge=self.name,
            dimension=self.dimension,
            label="supported" if supported else "unsupported",
            score=1.0 if supported else 0.0,
            rationale=(out or "").strip()[:240],
            is_ground_truth=False,
        )
