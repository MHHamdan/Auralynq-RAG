"""Detect and summarize entity communities in the knowledge graph.

Deterministic and offline for detection (networkx Louvain / greedy modularity
over a weighted, undirected projection of the KG). Summarization uses the
configured LLM and is best-effort — a failed summary never breaks the build.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import networkx as nx
from networkx.algorithms import community as nx_community

from auralynq.telemetry import get_logger

if TYPE_CHECKING:
    from auralynq.llm.base import LLM
    from auralynq.retrieval.pathrag.graph import KnowledgeGraph

_log = get_logger("auralynq.graphrag.communities")

_SUMMARY_SYSTEM = (
    "You write a concise 2-3 sentence summary of the THEME connecting a group of "
    "related entities in a knowledge graph. State what ties them together; do not "
    "invent facts beyond the entities and relations provided."
)


@dataclass
class Community:
    """A detected community of related entities with an optional LLM summary."""

    id: int
    level: int
    entities: list[str]  # display names
    relations: list[str]  # rendered "A -[rel]-> B" lines within the community
    size: int
    summary: str = ""
    sources: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _undirected_projection(kg: KnowledgeGraph) -> nx.Graph:
    """Collapse the MultiDiGraph into a simple weighted undirected graph."""
    ug: nx.Graph = nx.Graph()
    ug.add_nodes_from(kg.g.nodes())
    for u, v, data in kg.g.edges(data=True):
        if u == v:
            continue
        w = float(data.get("weight", 1.0))
        if ug.has_edge(u, v):
            ug[u][v]["weight"] += w
        else:
            ug.add_edge(u, v, weight=w)
    return ug


def detect_communities(
    kg: KnowledgeGraph, *, min_size: int = 3, algo: str = "louvain"
) -> list[Community]:
    """Detect communities, largest first, filtered by ``min_size``."""
    ug = _undirected_projection(kg)
    if ug.number_of_nodes() == 0:
        return []
    if algo == "greedy":
        raw = nx_community.greedy_modularity_communities(ug, weight="weight")
    else:  # louvain (seeded → deterministic)
        raw = nx_community.louvain_communities(ug, weight="weight", seed=42)

    communities: list[Community] = []
    for i, members in enumerate(sorted(raw, key=len, reverse=True)):
        if len(members) < min_size:
            continue
        names = sorted(kg.g.nodes[n].get("name", n) for n in members)
        relations: list[str] = []
        sources: set[str] = set()
        for u, v, data in kg.g.edges(data=True):
            if u in members and v in members:
                a = kg.g.nodes[u].get("name", u)
                b = kg.g.nodes[v].get("name", v)
                relations.append(f"{a} -[{data.get('relation', '—')}]-> {b}")
                for p in data.get("provenance", []):
                    if getattr(p, "source", ""):
                        sources.add(p.source)
        communities.append(
            Community(
                id=i,
                level=0,
                entities=names,
                relations=relations,
                size=len(members),
                sources=sorted(sources),
            )
        )
    return communities


def _summarize(community: Community, llm: LLM, max_tokens: int) -> str:
    ents = ", ".join(community.entities[:40])
    rels = "\n".join(community.relations[:40])
    prompt = (
        f"Entities: {ents}\n\nRelations:\n{rels or '(none)'}\n\n"
        "Summarize the theme connecting these entities in 2-3 sentences."
    )
    try:
        return llm.generate(
            prompt, system=_SUMMARY_SYSTEM, temperature=0.2, max_tokens=max_tokens
        ).strip()
    except Exception as exc:  # pragma: no cover - provider hiccup; non-fatal
        _log.warning("graphrag.summary_failed", community=community.id, error=str(exc))
        return ""


def synthesize_summaries(communities: list[Community], llm: LLM, *, max_tokens: int = 256) -> None:
    """Populate ``summary`` on each community in place (best-effort)."""
    for c in communities:
        c.summary = _summarize(c, llm, max_tokens)


def build_communities(
    kg: KnowledgeGraph,
    *,
    llm: LLM | None = None,
    settings: Any | None = None,
) -> list[Community]:
    """Detect, cap, summarize, and persist community summaries. Returns them."""
    from auralynq.config.settings import get_settings

    s = settings or get_settings()
    g = s.graphrag
    communities = detect_communities(kg, min_size=g.min_community_size, algo=g.algo)
    communities = communities[: g.max_communities]
    if communities:
        if llm is None:
            from auralynq.llm.factory import get_llm

            llm = get_llm()
        synthesize_summaries(communities, llm, max_tokens=g.max_summary_tokens)
    save_communities(communities, s.communities_path)
    _log.info("graphrag.communities_built", n=len(communities))
    return communities


def save_communities(communities: list[Community], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "communities": [c.as_dict() for c in communities]}
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_communities(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data.get("communities", [])
