"""T2-RAGBench adapter (arXiv:2506.12071).

Text-and-table financial QA. Sets ``requires_table_reasoning=True`` so the
corpus-type ablation (E) can isolate table behavior. No download.
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


class T2RAGBenchAdapter(BaseAdapter):
    name = "t2_ragbench"
    source = "arXiv:2506.12071"
    license = "see T2-RAGBench dataset card"

    def _load_raw(self) -> Iterable[dict[str, Any]]:
        path = _first_existing(self.root, ["t2_ragbench.jsonl", "data.jsonl"])
        if path is None:
            return
        yield from _iter_jsonl(path)

    def _normalize(self, raw: dict[str, Any], idx: int) -> NormalizedExample:
        return NormalizedExample(
            question_id=str(raw.get("id") or f"t2-{idx}"),
            question=str(raw.get("question") or raw.get("query") or ""),
            gold_answer=str(raw.get("answer") or raw.get("gold_answer") or ""),
            gold_contexts=list(raw.get("context") or raw.get("gold_contexts") or []),
            domain="finance",
            language="en",
            task_type="table_qa",
            requires_table_reasoning=True,
            requires_multihop=bool(raw.get("multi_hop", False)),
            metadata={"has_table": True},
        )
