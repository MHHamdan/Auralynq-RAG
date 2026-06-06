"""Abstention judge — did the system abstain when it should have (and vice versa)?

Uses available signal: the benchmark's ``requires_abstention`` label when present,
otherwise a groundedness proxy. Labels:
  * correct_abstention   — abstained and should have
  * unnecessary_abstention — abstained but evidence looked sufficient
  * should_have_abstained — answered but evidence looked insufficient
  * appropriate_answer   — answered with sufficient support
"""

from __future__ import annotations

from auralynq.research.evaluators.base import BaseJudge, JudgeInput, Verdict
from auralynq.research.metrics import groundedness_proxy


class AbstentionJudge(BaseJudge):
    name = "abstention"
    dimension = "abstention"
    requires_llm = False

    def __init__(self, support_floor: float = 0.5) -> None:
        self.support_floor = support_floor

    def judge(self, inp: JudgeInput) -> Verdict:
        # Prefer the dataset's answerability label when available.
        if inp.requires_abstention:
            should_abstain = True
            basis = "dataset label requires_abstention=True"
        else:
            g = groundedness_proxy(inp.answer, inp.contexts) if not inp.abstained else 0.0
            should_abstain = (not inp.contexts) or (not inp.abstained and g < self.support_floor)
            basis = f"groundedness/context proxy (g check vs {self.support_floor})"

        if inp.abstained and should_abstain:
            label = "correct_abstention"
        elif inp.abstained and not should_abstain:
            label = "unnecessary_abstention"
        elif (not inp.abstained) and should_abstain:
            label = "should_have_abstained"
        else:
            label = "appropriate_answer"

        score = 1.0 if label in ("correct_abstention", "appropriate_answer") else 0.0
        return Verdict(
            judge=self.name,
            dimension=self.dimension,
            label=label,
            score=score,
            rationale=basis,
        )
