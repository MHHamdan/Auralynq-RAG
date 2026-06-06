"""RGB adapter (arXiv:2309.01431) — focus on the negative-rejection testbed.

RGB probes four abilities; the **negative-rejection** testbed is the cleanest
public abstention signal: the gold passages do not support the query, so a
faithful system should reject ("not enough evidence"). We map such records to
``requires_abstention=True``. Other testbeds (noise robustness, information
integration, counterfactual) are carried through with the testbed in metadata.
No download (see docs/research/dataset-setup.md).
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


class RGBAdapter(BaseAdapter):
    name = "rgb"
    source = "arXiv:2309.01431 (chen700564/RGB)"
    license = "see chen700564/RGB repository"

    def _load_raw(self) -> Iterable[dict[str, Any]]:
        # RGB ships per-testbed json/jsonl (e.g. en_refuse.json for negative rejection).
        path = _first_existing(
            self.root, ["rgb.jsonl", "en_refuse.jsonl", "en.jsonl", "data.jsonl"]
        )
        if path is None:
            return
        yield from _iter_jsonl(path)

    @staticmethod
    def _is_negative_rejection(raw: dict[str, Any]) -> bool:
        testbed = str(raw.get("testbed") or raw.get("type") or "").lower()
        if "reject" in testbed or "negative" in testbed:
            return True
        # Heuristic fallback: no positive/supporting passages provided.
        positive = raw.get("positive") or raw.get("gold_contexts") or []
        return raw.get("answerable") is False or ("positive" in raw and not positive)

    def _normalize(self, raw: dict[str, Any], idx: int) -> NormalizedExample:
        ans = raw.get("answer")
        if isinstance(ans, list):
            ans = ans[0] if ans else ""
        contexts = list(raw.get("positive") or raw.get("docs") or raw.get("gold_contexts") or [])
        requires_abstention = self._is_negative_rejection(raw)
        return NormalizedExample(
            question_id=str(raw.get("id") or f"rgb-{idx}"),
            question=str(raw.get("query") or raw.get("question") or ""),
            gold_answer="" if requires_abstention else str(ans or ""),
            gold_contexts=[] if requires_abstention else contexts,
            domain="news",
            language=str(raw.get("language") or "en"),
            task_type="negative_rejection" if requires_abstention else "qa",
            requires_abstention=requires_abstention,
            metadata={
                "testbed": raw.get("testbed") or raw.get("type"),
                "n_negative_docs": len(raw.get("negative") or []),
            },
        )
