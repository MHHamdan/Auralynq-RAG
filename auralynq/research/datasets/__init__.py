"""Dataset adapter registry.

All adapters normalize to :class:`NormalizedExample`. Nothing here downloads data
automatically (see ``base.ResearchDataEnv`` / ``docs/research/dataset-setup.md``).
"""

from __future__ import annotations

from auralynq.research.datasets.ares_adapter import ARESAdapter
from auralynq.research.datasets.base import (
    BaseAdapter,
    DatasetUnavailable,
    NormalizedExample,
    ResearchDataEnv,
)
from auralynq.research.datasets.crag_adapter import CRAGAdapter
from auralynq.research.datasets.custom_corpus import CustomCorpusAdapter
from auralynq.research.datasets.mirage_adapter import MirageAdapter
from auralynq.research.datasets.ragbench import RAGBenchAdapter
from auralynq.research.datasets.t2_ragbench_adapter import T2RAGBenchAdapter

REGISTRY: dict[str, type[BaseAdapter]] = {
    CustomCorpusAdapter.name: CustomCorpusAdapter,
    CRAGAdapter.name: CRAGAdapter,
    RAGBenchAdapter.name: RAGBenchAdapter,
    MirageAdapter.name: MirageAdapter,
    T2RAGBenchAdapter.name: T2RAGBenchAdapter,
    ARESAdapter.name: ARESAdapter,
}


def get_adapter(name: str, env: ResearchDataEnv | None = None) -> BaseAdapter:
    if name == "mini":
        return CustomCorpusAdapter.mini()
    try:
        cls = REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"unknown dataset '{name}'. known: {sorted(REGISTRY)} (+ 'mini')") from exc
    return cls(env=env)


def list_datasets(env: ResearchDataEnv | None = None) -> list[dict[str, object]]:
    """Describe each registered dataset and whether local files are present."""
    env = env or ResearchDataEnv.from_env()
    rows: list[dict[str, object]] = [
        {
            "name": "mini",
            "source": "built-in synthetic",
            "available": True,
            "license": "n/a (synthetic)",
        }
    ]
    for name, cls in REGISTRY.items():
        inst = cls(env=env)
        rows.append(
            {
                "name": name,
                "source": inst.source,
                "available": inst.available(),
                "license": inst.license,
            }
        )
    return rows


__all__ = [
    "REGISTRY",
    "ARESAdapter",
    "BaseAdapter",
    "CRAGAdapter",
    "CustomCorpusAdapter",
    "DatasetUnavailable",
    "MirageAdapter",
    "NormalizedExample",
    "RAGBenchAdapter",
    "ResearchDataEnv",
    "T2RAGBenchAdapter",
    "get_adapter",
    "list_datasets",
]
