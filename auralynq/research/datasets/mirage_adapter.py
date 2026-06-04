"""MIRAGE-Bench adapter (arXiv:2410.13716, NAACL 2025).

Multilingual RAG (18 languages atop MIRACL). Crucially sets ``language`` per
example, which feeds Auralynq's language-mismatch trace feature in the C3 study.
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


class MirageAdapter(BaseAdapter):
    name = "mirage"
    source = "arXiv:2410.13716 (vectara/mirage-bench)"
    license = "see vectara/mirage-bench (Wikipedia/MIRACL terms)"

    def _load_raw(self) -> Iterable[dict[str, Any]]:
        path = _first_existing(self.root, ["mirage.jsonl", "data.jsonl"])
        if path is None:
            return
        yield from _iter_jsonl(path)

    def _normalize(self, raw: dict[str, Any], idx: int) -> NormalizedExample:
        return NormalizedExample(
            question_id=str(raw.get("query_id") or raw.get("id") or f"mirage-{idx}"),
            question=str(raw.get("query") or raw.get("question") or ""),
            gold_answer=str(raw.get("answer") or raw.get("gold_answer") or ""),
            gold_contexts=list(raw.get("positive_passages") or raw.get("gold_contexts") or []),
            domain="wikipedia",
            language=str(raw.get("language") or raw.get("lang") or "en"),
            task_type="multilingual_qa",
            metadata={"heuristic_features": raw.get("heuristic_features")},
        )
