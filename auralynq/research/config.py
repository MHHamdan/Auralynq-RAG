"""Research experiment configuration.

A :class:`ResearchConfig` is the single source of truth for one experimental
condition (a row in the ablation tables). Configs are authored as YAML under
``configs/research/`` and loaded here. A config is *applied* by materializing it
into ``AURALYNQ_*`` environment overrides and calling
:func:`auralynq.config.reload_settings`, so the existing pipeline honors it
without any rewiring (ADR-style: reuse the env-driven Settings).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

RetrievalMode = Literal[
    "dense",
    "sparse",
    "hybrid",
    "hybrid_rerank",
    "graph",
    "vector_graph",
    "vector_graph_rerank",
    "full_agentic",
]


class RetrievalCfg(BaseModel):
    mode: RetrievalMode = "hybrid"
    top_k: int = 20
    final_k: int = 6
    chunk_size: int = 800
    chunk_overlap: int = 120
    keyword: bool = True  # sparse/BM25 fusion on/off
    graph: bool = False  # PathRAG graph expansion on/off
    reranker: bool = False  # cross-encoder reranker on/off


class EmbeddingCfg(BaseModel):
    provider: str = "auto"  # auto|bge|hash|openai|ollama
    model: str = "BAAI/bge-m3"


class VectorCfg(BaseModel):
    backend: str = "auto"  # auto|qdrant|memory
    collection: str = "auralynq_research"


class LLMCfg(BaseModel):
    provider: str = "auto"  # auto|ollama|openai|anthropic|cohere|extractive
    model: str = "llama3.2:3b"
    temperature: float = 0.1
    max_tokens: int = 1024


class AbstentionCfg(BaseModel):
    # none: never abstain on sufficiency; threshold: raw score; heuristic: ESC;
    # calibrated: ESC + calibrator; judge: ESC + LLM judge assist.
    mode: Literal["none", "threshold", "heuristic", "calibrated", "judge"] = "heuristic"
    evidence_sufficiency: bool = True
    threshold: float = 0.5  # abstain when confidence < threshold
    citation_required: bool = True


class ResearchConfig(BaseModel):
    """One experimental condition."""

    name: str = "unnamed"
    description: str = ""
    seed: int = 42

    retrieval: RetrievalCfg = Field(default_factory=RetrievalCfg)
    embedding: EmbeddingCfg = Field(default_factory=EmbeddingCfg)
    vector: VectorCfg = Field(default_factory=VectorCfg)
    llm: LLMCfg = Field(default_factory=LLMCfg)
    abstention: AbstentionCfg = Field(default_factory=AbstentionCfg)

    web_search: bool = False
    voice: bool = False

    model_config = {"extra": "forbid"}

    # ---------------------------------------------------------------- io ----
    @classmethod
    def from_yaml(cls, path: str | Path) -> ResearchConfig:
        import yaml  # lazy: only needed when loading configs

        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls.model_validate(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResearchConfig:
        return cls.model_validate(data)

    def to_yaml(self, path: str | Path) -> None:
        import yaml

        Path(path).write_text(
            yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False),
            encoding="utf-8",
        )

    # ------------------------------------------------- env materialization ---
    def env_overrides(self) -> dict[str, str]:
        """Map this config onto ``AURALYNQ_*`` environment variables.

        Reranker off → ``AURALYNQ_RERANK__PROVIDER=none``. Graph/keyword/web/voice
        toggles are consumed by the runner directly (they change object wiring,
        not Settings fields), but are still echoed for provenance.
        """
        env: dict[str, str] = {
            "AURALYNQ_SEED": str(self.seed),
            "AURALYNQ_RETRIEVAL__TOP_K": str(self.retrieval.top_k),
            "AURALYNQ_RETRIEVAL__FINAL_K": str(self.retrieval.final_k),
            "AURALYNQ_EMBEDDING__PROVIDER": self.embedding.provider,
            "AURALYNQ_EMBEDDING__MODEL": self.embedding.model,
            "AURALYNQ_VECTOR__BACKEND": self.vector.backend,
            "AURALYNQ_VECTOR__COLLECTION": self.vector.collection,
            "AURALYNQ_LLM__PROVIDER": self.llm.provider,
            "AURALYNQ_LLM__MODEL": self.llm.model,
            "AURALYNQ_LLM__TEMPERATURE": str(self.llm.temperature),
            "AURALYNQ_LLM__MAX_TOKENS": str(self.llm.max_tokens),
            "AURALYNQ_RERANK__PROVIDER": "auto" if self.retrieval.reranker else "none",
        }
        return env

    def apply(self) -> None:
        """Set env overrides and reload the cached Settings for this process."""
        from auralynq.config import reload_settings

        os.environ.update(self.env_overrides())
        reload_settings()

    # ----------------------------------------------------------- helpers ----
    @property
    def use_graph(self) -> bool:
        return self.retrieval.graph or self.retrieval.mode in (
            "graph",
            "vector_graph",
            "vector_graph_rerank",
            "full_agentic",
        )

    @property
    def use_reranker(self) -> bool:
        return self.retrieval.reranker or self.retrieval.mode in (
            "hybrid_rerank",
            "vector_graph_rerank",
            "full_agentic",
        )

    @property
    def use_keyword(self) -> bool:
        return self.retrieval.keyword and self.retrieval.mode not in ("dense", "graph")


def load_config(path: str | Path) -> ResearchConfig:
    return ResearchConfig.from_yaml(path)
