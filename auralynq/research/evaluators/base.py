"""Evaluation judges — base classes + agreement reporting.

Judges score one (question, answer, evidence) record along a dimension
("supported", "citations_correct", "should_abstain", ...). LLM judges are
**optional** and are **never** treated as ground truth (see MT-Bench / GroUSE in
the literature matrix). The framework reports inter-judge agreement so judge
reliability is visible, not assumed.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class JudgeInput(BaseModel):
    question: str
    answer: str
    contexts: list[str] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    gold_answer: str = ""
    gold_contexts: list[str] = Field(default_factory=list)
    abstained: bool = False
    requires_abstention: bool = False
    language: str = "en"
    metadata: dict[str, Any] = Field(default_factory=dict)


class Verdict(BaseModel):
    judge: str
    dimension: str
    label: str  # e.g. supported | unsupported | correct | should_abstain | ...
    score: float = 0.0  # 0..1
    rationale: str = ""
    is_ground_truth: bool = False  # judges are NOT ground truth unless from labels

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class BaseJudge(ABC):
    name = "base"
    dimension = "generic"
    #: heuristic judges run offline; LLM judges require a provider
    requires_llm: bool = False

    @abstractmethod
    def judge(self, inp: JudgeInput) -> Verdict: ...

    def judge_many(self, inputs: list[JudgeInput]) -> list[Verdict]:
        return [self.judge(i) for i in inputs]


# ----------------------------------------------------------------- agreement ---
def cohen_kappa(labels_a: list[str], labels_b: list[str]) -> float:
    """Cohen's kappa for two raters over matched nominal labels."""
    if not labels_a or len(labels_a) != len(labels_b):
        return 0.0
    n = len(labels_a)
    cats = set(labels_a) | set(labels_b)
    po = sum(1 for a, b in zip(labels_a, labels_b, strict=True) if a == b) / n
    pe = 0.0
    for c in cats:
        pa = labels_a.count(c) / n
        pb = labels_b.count(c) / n
        pe += pa * pb
    if abs(1 - pe) < 1e-9:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def krippendorff_alpha_nominal(rater_labels: list[list[str]]) -> float:
    """Krippendorff's alpha (nominal) for >=2 raters over the same items.

    ``rater_labels[r][i]`` is rater r's label for item i. Simplified estimator
    (no missing data). Returns 1.0 for perfect agreement, ~0 for chance.
    """
    if len(rater_labels) < 2:
        return 1.0
    n_items = len(rater_labels[0])
    if n_items == 0:
        return 1.0
    # observed disagreement
    do_num, do_den = 0, 0
    for i in range(n_items):
        col = [r[i] for r in rater_labels]
        m = len(col)
        for x in range(m):
            for y in range(m):
                if x != y:
                    do_num += int(col[x] != col[y])
        do_den += m * (m - 1)
    do = do_num / do_den if do_den else 0.0
    # expected disagreement from the global label distribution
    all_labels = [lab for r in rater_labels for lab in r]
    n = len(all_labels)
    counts: dict[str, int] = {}
    for lab in all_labels:
        counts[lab] = counts.get(lab, 0) + 1
    de = 1.0 - sum((c / n) ** 2 for c in counts.values())
    if de < 1e-9:
        return 1.0
    return 1.0 - do / de


def agreement_report(verdicts_by_judge: dict[str, list[Verdict]]) -> dict[str, Any]:
    """Pairwise Cohen's kappa + overall Krippendorff alpha across judges.

    All judge label-lists must be aligned on the same items in the same order.
    """
    judges = list(verdicts_by_judge)
    label_lists = {j: [v.label for v in verdicts_by_judge[j]] for j in judges}
    pairwise: dict[str, float] = {}
    for i in range(len(judges)):
        for k in range(i + 1, len(judges)):
            a, b = judges[i], judges[k]
            pairwise[f"{a}__vs__{b}"] = round(cohen_kappa(label_lists[a], label_lists[b]), 4)
    alpha = krippendorff_alpha_nominal([label_lists[j] for j in judges])
    return {
        "judges": judges,
        "pairwise_cohen_kappa": pairwise,
        "krippendorff_alpha": round(alpha, 4),
        "n_items": len(next(iter(label_lists.values()))) if label_lists else 0,
        "note": "LLM-judge labels are not ground truth; report agreement, not accuracy.",
    }


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))
