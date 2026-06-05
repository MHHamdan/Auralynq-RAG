"""Custom local corpus adapter + a built-in synthetic mini benchmark.

The mini benchmark needs no files and powers the offline smoke experiment. It
deliberately includes *unanswerable* questions so abstention behavior is exercised
honestly (never tuned to make the system look better).
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

# A tiny, self-contained QA set grounded in Auralynq's own documented behavior.
# `supporting` are source-name substrings; `requires_abstention` marks items the
# corpus genuinely cannot answer.
_MINI: list[dict[str, Any]] = [
    {
        "question": "How does PathRAG prune relational paths?",
        "gold_answer": "Flow-based resource-allocation pruning over relational paths.",
        "supporting": ["pathrag"],
        "domain": "rag",
        "requires_abstention": False,
    },
    {
        "question": "What removes redundant retrieved chunks in Auralynq?",
        "gold_answer": "Maximal marginal relevance (MMR).",
        "supporting": ["mmr", "auralynq"],
        "domain": "rag",
        "requires_abstention": False,
    },
    {
        "question": "Which vector store backends does Auralynq support?",
        "gold_answer": "Qdrant and an in-memory store.",
        "supporting": ["vectorstore", "qdrant"],
        "domain": "systems",
        "requires_abstention": False,
    },
    {
        "question": "What is the reciprocal-rank-fusion constant used for hybrid fusion?",
        "gold_answer": "An rrf_k constant (default 60) in reciprocal rank fusion.",
        "supporting": ["fusion", "hybrid"],
        "domain": "rag",
        "requires_abstention": False,
    },
    {
        "question": "What were the GDP figures of Atlantis in fiscal year 3025?",
        "gold_answer": "",
        "supporting": [],
        "domain": "finance",
        "requires_abstention": True,
    },
    {
        "question": "Who is the current CEO of the fictional company Zibblecorp?",
        "gold_answer": "",
        "supporting": [],
        "domain": "general",
        "requires_abstention": True,
    },
]


class CustomCorpusAdapter(BaseAdapter):
    name = "custom_corpus"
    source = "local (user-provided)"
    license = "user-owned"

    def __init__(self, *args, use_mini: bool = False, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._use_mini = use_mini

    def available(self) -> bool:
        if self._use_mini:
            return True
        return super().available()

    def _load_raw(self) -> Iterable[dict[str, Any]]:
        if self._use_mini:
            yield from _MINI
            return
        path = _first_existing(self.root, ["qa.jsonl", "questions.jsonl"])
        if path is None:
            return
        yield from _iter_jsonl(path)

    def _normalize(self, raw: dict[str, Any], idx: int) -> NormalizedExample:
        supporting = raw.get("supporting") or raw.get("source_documents") or []
        return NormalizedExample(
            question_id=str(raw.get("question_id") or raw.get("id") or f"custom-{idx}"),
            question=raw["question"],
            gold_answer=str(raw.get("gold_answer") or raw.get("answer") or ""),
            gold_contexts=list(raw.get("gold_contexts") or []),
            source_documents=list(supporting),
            domain=str(raw.get("domain", "general")),
            language=str(raw.get("language", "en")),
            task_type=str(raw.get("task_type", "qa")),
            requires_abstention=bool(raw.get("requires_abstention", False)),
            requires_multihop=bool(raw.get("requires_multihop", False)),
            requires_table_reasoning=bool(raw.get("requires_table_reasoning", False)),
            metadata={"supporting": list(supporting)},
        )

    @classmethod
    def mini(cls) -> CustomCorpusAdapter:
        """Built-in synthetic mini benchmark (no files; powers the smoke run)."""
        return cls(use_mini=True)
