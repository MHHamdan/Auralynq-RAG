"""Consistency judge — is the answer internally consistent with its evidence?

Offline proxy: low groundedness combined with confident phrasing, or explicit
negation patterns relative to context, flag a potential inconsistency. This is a
*screening* signal, not ground truth.
"""

from __future__ import annotations

import re

from auralynq.research.evaluators.base import BaseJudge, JudgeInput, Verdict
from auralynq.research.metrics import groundedness_proxy

_HEDGES = re.compile(r"\b(maybe|perhaps|might|possibly|i think|not sure)\b", re.I)


class ConsistencyJudge(BaseJudge):
    name = "consistency"
    dimension = "consistency"
    requires_llm = False

    def judge(self, inp: JudgeInput) -> Verdict:
        if inp.abstained:
            return Verdict(
                judge=self.name,
                dimension=self.dimension,
                label="abstained",
                rationale="system abstained",
            )
        g = groundedness_proxy(inp.answer, inp.contexts)
        hedged = bool(_HEDGES.search(inp.answer))
        # Inconsistent: little support yet asserted without hedging.
        if g < 0.3 and not hedged and len(inp.answer.split()) > 8:
            label, score = "inconsistent", round(1.0 - g, 4)
            rationale = f"low support (g={g:.2f}) but confidently asserted"
        else:
            label, score = "consistent", round(g, 4)
            rationale = f"support g={g:.2f}, hedged={hedged}"
        return Verdict(
            judge=self.name,
            dimension=self.dimension,
            label=label,
            score=score,
            rationale=rationale,
        )
