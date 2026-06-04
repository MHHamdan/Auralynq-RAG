"""Benchmark dataset adapters: a common schema + a no-auto-download policy.

Every adapter normalizes its source into :class:`NormalizedExample`. Real data is
loaded only from ``AURALYNQ_RESEARCH__DATA_DIR`` (default ``./data/research``);
network downloads happen *only* when ``AURALYNQ_RESEARCH__ALLOW_DATASET_DOWNLOAD``
is true and are capped by ``AURALYNQ_RESEARCH__MAX_EXAMPLES``. See
``docs/research/dataset-setup.md``.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class NormalizedExample(BaseModel):
    """The single schema every benchmark is mapped into."""

    question_id: str
    question: str
    gold_answer: str = ""
    gold_contexts: list[str] = Field(default_factory=list)
    source_documents: list[str] = Field(default_factory=list)
    domain: str = "general"
    language: str = "en"
    task_type: str = "qa"
    requires_abstention: bool = False
    requires_multihop: bool = False
    requires_table_reasoning: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchDataEnv(BaseModel):
    """Env-driven knobs governing dataset access (no secrets here)."""

    data_dir: Path = Path("./data/research")
    allow_download: bool = False
    max_examples: int = 100

    @classmethod
    def from_env(cls) -> ResearchDataEnv:
        return cls(
            data_dir=Path(os.getenv("AURALYNQ_RESEARCH__DATA_DIR", "./data/research")),
            allow_download=os.getenv("AURALYNQ_RESEARCH__ALLOW_DATASET_DOWNLOAD", "false").lower()
            in ("1", "true", "yes"),
            max_examples=int(os.getenv("AURALYNQ_RESEARCH__MAX_EXAMPLES", "100")),
        )


class DatasetUnavailable(RuntimeError):
    """Raised when a dataset's files are absent and download is disabled."""


class BaseAdapter(ABC):
    """Base class for all benchmark adapters."""

    name: str = "base"
    #: human-facing pointer (arXiv id / URL) recorded into provenance + metadata
    source: str = ""
    #: dataset license string echoed into every example's metadata
    license: str = "see dataset-setup.md"

    def __init__(self, env: ResearchDataEnv | None = None) -> None:
        self.env = env or ResearchDataEnv.from_env()

    @property
    def root(self) -> Path:
        return self.env.data_dir / self.name

    def available(self) -> bool:
        """Whether local files exist for this dataset."""
        return self.root.exists() and any(self.root.iterdir())

    @abstractmethod
    def _load_raw(self) -> Iterable[dict[str, Any]]:
        """Yield raw records from local files (no network)."""

    @abstractmethod
    def _normalize(self, raw: dict[str, Any], idx: int) -> NormalizedExample:
        """Map one raw record into the common schema."""

    def load(self, limit: int | None = None) -> list[NormalizedExample]:
        """Load up to ``limit`` (default: env cap) normalized examples."""
        if not self.available():
            raise DatasetUnavailable(
                f"dataset '{self.name}' not found under {self.root}. "
                f"See docs/research/dataset-setup.md. "
                f"(download enabled={self.env.allow_download})"
            )
        cap = limit if limit is not None else self.env.max_examples
        out: list[NormalizedExample] = []
        for i, raw in enumerate(self._load_raw()):
            if len(out) >= cap:
                break
            ex = self._normalize(raw, i)
            ex.metadata.setdefault("dataset", self.name)
            ex.metadata.setdefault("source", self.source)
            ex.metadata.setdefault("license", self.license)
            out.append(ex)
        return out

    # convenience for tests / mocks: normalize an in-memory list
    def normalize_records(self, records: Iterable[dict[str, Any]]) -> list[NormalizedExample]:
        return [self._normalize(r, i) for i, r in enumerate(records)]


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    import json

    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def _first_existing(root: Path, names: list[str]) -> Path | None:
    for n in names:
        p = root / n
        if p.exists():
            return p
    # fall back to any jsonl in the dir
    if root.exists():
        for p in sorted(root.glob("*.jsonl")):
            return p
    return None
