"""Populate the bi-temporal belief store from the knowledge graph at ingest.

Each KG relation ``(entity) -[relation]-> (object)`` becomes a bi-temporal
*claim*. Valid-time (``valid_from``) is taken from the supporting chunk's
``authored_at`` metadata when present (the document's effective date); ingest-time
is stamped now.

Revision policy (avoids destroying genuinely multi-valued facts):

* **Functional** relations — a single distinct object for an (entity, predicate)
  in this corpus — are recorded with :meth:`BeliefStore.revise`, so a *changed*
  value from a later ingest supersedes the prior one and the timeline shows the
  revision. ``revise`` only supersedes an *open* prior claim whose object differs,
  and same-value re-ingests are idempotent, so re-indexing is a no-op.
* **Multi-valued** relations — several distinct objects for one (entity,
  predicate) — are recorded with :meth:`BeliefStore.record_claim` (accumulate;
  never supersede co-valid facts).
"""

from __future__ import annotations

from collections import defaultdict

from auralynq.beliefs.store import BeliefStore
from auralynq.ingest.models import Chunk
from auralynq.retrieval.pathrag.graph import KnowledgeGraph, Provenance


def _valid_from(provs: list[Provenance], chunk_by_id: dict[str, Chunk]) -> str | None:
    """Earliest ``authored_at`` across an edge's supporting chunks, or None."""
    dates: list[str] = []
    for p in provs:
        c = chunk_by_id.get(p.chunk_id)
        if c is not None:
            authored = c.metadata.get("authored_at")
            if authored:
                dates.append(str(authored))
    return min(dates) if dates else None


def _doc_id(provs: list[Provenance], chunk_by_id: dict[str, Chunk]) -> str:
    for p in provs:
        c = chunk_by_id.get(p.chunk_id)
        if c is not None and c.doc_id:
            return c.doc_id
    return ""


def populate_beliefs(kg: KnowledgeGraph, chunks: list[Chunk], store: BeliefStore) -> int:
    """Record/revise belief claims from every KG relation. Returns claims touched."""
    chunk_by_id = {c.id: c for c in chunks}

    # Group edges by (entity_key, relation) to detect functional vs multi-valued.
    grouped: dict[tuple[str, str], list[tuple[str, list[Provenance]]]] = defaultdict(list)
    for src, _, data in kg.g.edges(data=True):
        relation = data.get("relation", "")
        if not relation:
            continue
        dst = data.get("_dst", "")
        dst_name = kg.g.nodes[dst].get("name", dst) if kg.g.has_node(dst) else dst
        grouped[(src, relation)].append((dst_name, data.get("provenance", [])))

    touched = 0
    for (src, relation), objs in grouped.items():
        src_name = kg.g.nodes[src].get("name", src) if kg.g.has_node(src) else src
        distinct_objects = {o for o, _ in objs}
        functional = len(distinct_objects) == 1
        for dst_name, provs in objs:
            sources = sorted({p.source for p in provs if p.source})
            source = ", ".join(sources)
            valid_from = _valid_from(provs, chunk_by_id)
            doc_id = _doc_id(provs, chunk_by_id)
            if functional:
                store.revise(
                    src_name,
                    relation,
                    dst_name,
                    source=source,
                    doc_id=doc_id,
                    valid_from=valid_from,
                )
            else:
                store.record_claim(
                    src_name,
                    relation,
                    dst_name,
                    source=source,
                    doc_id=doc_id,
                    valid_from=valid_from,
                )
            touched += 1
    return touched
