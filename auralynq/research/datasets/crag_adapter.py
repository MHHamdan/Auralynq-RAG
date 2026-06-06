"""CRAG -- Comprehensive RAG Benchmark adapter (arXiv:2406.04744).

Maps CRAG's web+KG factual QA into the common schema. CRAG provides answerability
signals (e.g. "invalid"/"missing" answers) that we surface as
``requires_abstention`` so the abstention study can use real labels. No download.
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

_ABSTAIN_MARKERS = {"invalid", "i don't know", "i dont know", "", "n/a", "none"}


class CRAGAdapter(BaseAdapter):
    name = "crag"
    source = "arXiv:2406.04744 (facebookresearch/CRAG)"
    license = "see facebookresearch/CRAG (CC-BY-NC 4.0 per repo)"

    def _load_raw(self) -> Iterable[dict[str, Any]]:
        path = _first_existing(self.root, ["crag.jsonl", "questions.jsonl", "data.jsonl"])
        if path is None:
            return
        yield from _iter_jsonl(path)

    def _normalize(self, raw: dict[str, Any], idx: int) -> NormalizedExample:
        ans = str(raw.get("answer") or raw.get("gold_answer") or "").strip()
        # CRAG question types include simple/conditional/comparison/aggregation/...
        qtype = str(raw.get("question_type") or raw.get("static_or_dynamic") or "qa")
        requires_abstention = ans.lower() in _ABSTAIN_MARKERS
        return NormalizedExample(
            question_id=str(raw.get("interaction_id") or raw.get("id") or f"crag-{idx}"),
            question=raw["query"] if "query" in raw else raw["question"],
            gold_answer=ans,
            gold_contexts=list(
                raw.get("search_results_snippets") or raw.get("gold_contexts") or []
            ),
            source_documents=list(raw.get("source_documents") or []),
            domain=str(raw.get("domain", "open")),
            language="en",
            task_type=qtype,
            requires_abstention=requires_abstention,
            requires_multihop=qtype in ("multi-hop", "comparison", "aggregation"),
            metadata={
                "dynamism": raw.get("static_or_dynamic"),
                "uses_web": True,
                "uses_kg": bool(raw.get("kg_results")),
            },
        )
