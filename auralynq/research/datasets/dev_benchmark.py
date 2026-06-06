"""Built-in `dev` benchmark — a larger, reproducible, committable QA set.

Unlike a downloaded benchmark, the corpus *and* the questions ship in this module
so an ablation runs identically anywhere, offline, at $0. It is intentionally
modest (development-scale) and is **not** a paper result — it exists to exercise
the retrieval/abstention ablation with real signal:

  * answerable single-hop questions (grounded in the corpus),
  * multi-hop questions (need two documents),
  * honestly **unanswerable** questions (corpus does not cover them) that a
    faithful system must reject.

The corpus is exposed via :meth:`DevBenchmarkAdapter.corpus` so the ablation
script can write it to a data dir and index it before running.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from auralynq.research.datasets.base import BaseAdapter, NormalizedExample

# --- grounding corpus (filename -> text). Self-consistent, factual about Auralynq.
CORPUS: dict[str, str] = {
    "pathrag.md": (
        "PathRAG is a graph-based retrieval method. It first retrieves seed nodes, "
        "then expands relational paths between them, then applies flow-based "
        "resource-allocation pruning to keep only reliable paths. Each path is "
        "scored by a reliability value and rendered to text for prompting."
    ),
    "fusion.md": (
        "Auralynq hybrid retrieval fuses dense and sparse rankings using reciprocal "
        "rank fusion (RRF) with a constant rrf_k of 60. Maximal marginal relevance "
        "(MMR) then removes redundant chunks using an mmr_lambda of 0.6."
    ),
    "rerank.md": (
        "After fusion, Auralynq optionally reranks candidates with a cross-encoder "
        "reranker, by default BAAI/bge-reranker-v2-m3. Reranking reorders the top "
        "candidates before the final selection of context chunks."
    ),
    "embeddings.md": (
        "The default embedding model in Auralynq is BAAI/bge-m3 with an embedding "
        "dimension of 1024. A deterministic hashing embedder is used as an offline "
        "fallback for tests and zero-cost runs."
    ),
    "vectorstore.md": (
        "Auralynq supports two vector store backends: Qdrant for production "
        "deployments and an in-memory store for local development and tests. The "
        "default Qdrant collection is named auralynq."
    ),
    "agent.md": (
        "The Auralynq agent runs a plan, route, retrieve, fuse, critic loop with a "
        "maximum of three iterations and a latency budget of fifteen seconds. It "
        "routes a query to a fast path or a deep PathRAG path."
    ),
    "voice.md": (
        "Auralynq voice input uses faster-whisper for automatic speech recognition "
        "and Kokoro for text to speech. Voice activity detection and speaker "
        "diarization are enabled by default at a 16 kHz sample rate."
    ),
    "citations.md": (
        "Auralynq answers cite every claim with bracketed markers such as [1] that "
        "refer to numbered context items. If the context lacks the answer, the "
        "system states it does not have enough evidence rather than guessing."
    ),
    "observability.md": (
        "Every Auralynq query emits a trace of typed spans for routing, retrieval, "
        "fusion, synthesis, self-check and citation validation. Traces can be "
        "exported to Phoenix or Langfuse for inspection."
    ),
    "geography.md": (
        "Paris is the capital of France, a country in Western Europe. The Seine "
        "river flows through Paris. Berlin is the capital of Germany."
    ),
}

# --- QA. `supporting` are source-name substrings (for retrieval metrics).
_QA: list[dict[str, Any]] = [
    # answerable single-hop
    {
        "q": "How does PathRAG prune relational paths?",
        "a": "Flow-based resource-allocation pruning.",
        "s": ["pathrag"],
    },
    {
        "q": "What constant does reciprocal rank fusion use in Auralynq?",
        "a": "An rrf_k of 60.",
        "s": ["fusion"],
    },
    {
        "q": "What removes redundant retrieved chunks?",
        "a": "Maximal marginal relevance (MMR).",
        "s": ["fusion"],
    },
    {
        "q": "What is the default reranker model in Auralynq?",
        "a": "BAAI/bge-reranker-v2-m3.",
        "s": ["rerank"],
    },
    {
        "q": "What is the default embedding model and dimension?",
        "a": "BAAI/bge-m3 with dimension 1024.",
        "s": ["embeddings"],
    },
    {
        "q": "Which vector store backends does Auralynq support?",
        "a": "Qdrant and an in-memory store.",
        "s": ["vectorstore"],
    },
    {
        "q": "What is the agent's maximum number of iterations?",
        "a": "Three iterations.",
        "s": ["agent"],
    },
    {"q": "What latency budget does the agent use?", "a": "Fifteen seconds.", "s": ["agent"]},
    {
        "q": "Which ASR engine does Auralynq use for voice input?",
        "a": "faster-whisper.",
        "s": ["voice"],
    },
    {"q": "Which text-to-speech engine does Auralynq use?", "a": "Kokoro.", "s": ["voice"]},
    {
        "q": "How does Auralynq mark claims in an answer?",
        "a": "With bracketed citation markers like [1].",
        "s": ["citations"],
    },
    {
        "q": "Where can Auralynq traces be exported?",
        "a": "To Phoenix or Langfuse.",
        "s": ["observability"],
    },
    {"q": "What is the capital of France?", "a": "Paris.", "s": ["geography"]},
    {"q": "What river flows through Paris?", "a": "The Seine.", "s": ["geography"]},
    {"q": "What is the default Qdrant collection name?", "a": "auralynq.", "s": ["vectorstore"]},
    {"q": "What mmr_lambda value does Auralynq use?", "a": "0.6.", "s": ["fusion"]},
    {
        "q": "What is the offline fallback embedder?",
        "a": "A deterministic hashing embedder.",
        "s": ["embeddings"],
    },
    {"q": "At what sample rate does Auralynq process voice?", "a": "16 kHz.", "s": ["voice"]},
    # multi-hop (need two docs)
    {
        "q": "After fusion with RRF, what reranker reorders candidates before selection?",
        "a": "A cross-encoder reranker (bge-reranker-v2-m3).",
        "s": ["fusion", "rerank"],
        "mh": True,
    },
    {
        "q": "Which retrieval path does the agent route to for graph reasoning, "
        "and how does that path prune paths?",
        "a": "The deep PathRAG path, which uses flow-based pruning.",
        "s": ["agent", "pathrag"],
        "mh": True,
    },
    # honestly unanswerable (corpus does not cover these)
    {
        "q": "What were the GDP figures of Atlantis in fiscal year 3025?",
        "a": "",
        "s": [],
        "abst": True,
    },
    {
        "q": "Who is the current CEO of the fictional company Zibblecorp?",
        "a": "",
        "s": [],
        "abst": True,
    },
    {
        "q": "What is the airspeed velocity of an unladen swallow on Mars?",
        "a": "",
        "s": [],
        "abst": True,
    },
    {
        "q": "What is Auralynq's pricing for its enterprise SaaS tier?",
        "a": "",
        "s": [],
        "abst": True,
    },
]


class DevBenchmarkAdapter(BaseAdapter):
    name = "dev"
    source = "built-in development benchmark (Auralynq)"
    license = "Apache-2.0 (project-owned synthetic set)"

    def available(self) -> bool:
        return True

    @classmethod
    def corpus(cls) -> dict[str, str]:
        return dict(CORPUS)

    def _load_raw(self) -> Iterable[dict[str, Any]]:
        yield from _QA

    def _normalize(self, raw: dict[str, Any], idx: int) -> NormalizedExample:
        supporting = list(raw.get("s") or [])
        return NormalizedExample(
            question_id=f"dev-{idx:03d}",
            question=raw["q"],
            gold_answer=str(raw.get("a") or ""),
            source_documents=supporting,
            domain="auralynq" if supporting else "general",
            language="en",
            task_type="qa",
            requires_abstention=bool(raw.get("abst", False)),
            requires_multihop=bool(raw.get("mh", False)),
            metadata={"supporting": supporting},
        )
