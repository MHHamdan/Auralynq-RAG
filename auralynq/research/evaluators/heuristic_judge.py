"""Heuristic support judge — offline, deterministic, no LLM.

Labels an answer 'supported' or 'unsupported' from token-overlap groundedness.
A transparent baseline to compare LLM judges against (judge-agreement study).
"""

from __future__ import annotations

from auralynq.research.evaluators.base import BaseJudge, JudgeInput, Verdict
from auralynq.research.metrics import groundedness_proxy


class HeuristicJudge(BaseJudge):
    name = "heuristic"
    dimension = "support"
    requires_llm = False

    def __init__(self, threshold: float = 0.5) -> None:
        self.threshold = threshold

    def judge(self, inp: JudgeInput) -> Verdict:
        if inp.abstained:
            return Verdict(
                judge=self.name,
                dimension=self.dimension,
                label="abstained",
                score=0.0,
                rationale="system abstained; no answer to support-check",
            )
        g = groundedness_proxy(inp.answer, inp.contexts)
        supported = g >= self.threshold
        return Verdict(
            judge=self.name,
            dimension=self.dimension,
            label="supported" if supported else "unsupported",
            score=round(g, 4),
            rationale=f"groundedness_proxy={g:.2f} (token overlap with contexts)",
        )
