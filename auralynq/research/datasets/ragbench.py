"""RAGBench adapter (arXiv:2407.11005).

RAGBench ships TRACe annotations (uTilization, Relevance, Adherence,
Completeness). We carry those into ``metadata`` so they can be compared against
Auralynq's own sufficiency/groundedness features (adherence ~ groundedness,
completeness ~ answer coverage). No download.
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


class RAGBenchAdapter(BaseAdapter):
    name = "ragbench"
    source = "arXiv:2407.11005 (rungalileo/ragbench)"
    license = "see rungalileo/ragbench dataset card"

    def _load_raw(self) -> Iterable[dict[str, Any]]:
        path = _first_existing(self.root, ["ragbench.jsonl", "data.jsonl"])
        if path is None:
            return
        yield from _iter_jsonl(path)

    def _normalize(self, raw: dict[str, Any], idx: int) -> NormalizedExample:
        return NormalizedExample(
            question_id=str(raw.get("id") or f"ragbench-{idx}"),
            question=str(raw.get("question") or raw.get("query") or ""),
            gold_answer=str(raw.get("response") or raw.get("gold_answer") or ""),
            gold_contexts=list(raw.get("documents") or raw.get("gold_contexts") or []),
            domain=str(raw.get("dataset") or raw.get("domain") or "industry"),
            language="en",
            task_type="qa",
            requires_abstention=bool(raw.get("unanswerable", False)),
            metadata={
                "trace": {
                    "utilization": raw.get("utilization"),
                    "relevance": raw.get("relevance_score"),
                    "adherence": raw.get("adherence_score"),
                    "completeness": raw.get("completeness_score"),
                }
            },
        )
