"""Citation judge — are the answer's citations correct/sufficient? (offline)."""

from __future__ import annotations

from auralynq.research.evaluators.base import BaseJudge, JudgeInput, Verdict
from auralynq.research.metrics import citation_metrics_proxy


class CitationJudge(BaseJudge):
    name = "citation"
    dimension = "citation"
    requires_llm = False

    def __init__(self, precision_floor: float = 0.5) -> None:
        self.precision_floor = precision_floor

    def judge(self, inp: JudgeInput) -> Verdict:
        if inp.abstained:
            return Verdict(
                judge=self.name,
                dimension=self.dimension,
                label="abstained",
                rationale="system abstained; no citations to check",
            )
        m = citation_metrics_proxy(inp.answer, inp.citations, inp.contexts)
        if m["citation_coverage"] <= 0.0:
            label = "uncited"
        elif m["citation_precision_proxy"] >= self.precision_floor:
            label = "correct"
        else:
            label = "incorrect"
        return Verdict(
            judge=self.name,
            dimension=self.dimension,
            label=label,
            score=m["citation_precision_proxy"],
            rationale=(
                f"coverage={m['citation_coverage']:.2f} "
                f"precision_proxy={m['citation_precision_proxy']:.2f} "
                f"recall_proxy={m['citation_recall_proxy']:.2f}"
            ),
        )
