"""ARES adapter (arXiv:2311.09476).

ARES is primarily an *evaluation framework* (trained judges + PPI). We use its
labeled (query, context, answer, relevance/faithfulness) tuples to cross-check
our own judges in the judge-agreement study (C3), not as a primary QA set.
No download.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from auralynq.research.datasets.base import (
    BaseAdapter,
    NormalizedExample,
    _first_existing,
    _iter_jsonl,
)


class ARESAdapter(BaseAdapter):
    name = "ares"
    source = "arXiv:2311.09476 (stanford-futuredata/ARES)"
    license = "see ARES repository"

    def _load_raw(self) -> Iterable[dict[str, Any]]:
        path = _first_existing(self.root, ["ares.jsonl", "data.jsonl"])
        if path is None:
            return
        yield from _iter_jsonl(path)

    def _normalize(self, raw: dict[str, Any], idx: int) -> NormalizedExample:
        doc = raw.get("document")
        gold_contexts = [doc] if doc else list(raw.get("gold_contexts") or [])
        return NormalizedExample(
            question_id=str(raw.get("id") or f"ares-{idx}"),
            question=str(raw.get("query") or raw.get("question") or ""),
            gold_answer=str(raw.get("answer") or ""),
            gold_contexts=gold_contexts,
            domain=str(raw.get("domain", "general")),
            language="en",
            task_type="judge_calibration",
            metadata={
                "context_relevance": raw.get("context_relevance"),
                "answer_faithfulness": raw.get("answer_faithfulness"),
                "answer_relevance": raw.get("answer_relevance"),
            },
        )
