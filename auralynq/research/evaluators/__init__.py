"""Evaluation judges registry.

Heuristic judges run offline; the LLM judge is optional and is never treated as
ground truth. Use :func:`agreement_report` to quantify judge reliability.
"""

from __future__ import annotations

from auralynq.research.evaluators.abstention_judge import AbstentionJudge
from auralynq.research.evaluators.base import (
    BaseJudge,
    JudgeInput,
    Verdict,
    agreement_report,
    cohen_kappa,
    krippendorff_alpha_nominal,
)
from auralynq.research.evaluators.citation_judge import CitationJudge
from auralynq.research.evaluators.consistency_judge import ConsistencyJudge
from auralynq.research.evaluators.heuristic_judge import HeuristicJudge
from auralynq.research.evaluators.llm_judge import LLMJudge

JUDGES: dict[str, type[BaseJudge]] = {
    HeuristicJudge.name: HeuristicJudge,
    CitationJudge.name: CitationJudge,
    ConsistencyJudge.name: ConsistencyJudge,
    AbstentionJudge.name: AbstentionJudge,
    LLMJudge.name: LLMJudge,
}


def get_judge(name: str, **kwargs) -> BaseJudge:
    return JUDGES[name](**kwargs)


def offline_judges() -> list[BaseJudge]:
    """All non-LLM judges (deterministic, $0)."""
    return [cls() for name, cls in JUDGES.items() if not cls.requires_llm]


__all__ = [
    "JUDGES",
    "AbstentionJudge",
    "BaseJudge",
    "CitationJudge",
    "ConsistencyJudge",
    "HeuristicJudge",
    "JudgeInput",
    "LLMJudge",
    "Verdict",
    "agreement_report",
    "cohen_kappa",
    "get_judge",
    "krippendorff_alpha_nominal",
    "offline_judges",
]
