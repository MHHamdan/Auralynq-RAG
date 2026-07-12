"""Connector sync engine — cursor persistence + incremental index + pruning.

Generalizes the Watch Folder's reconciliation to remote sources: pull changed
docs since the stored cursor, index them (idempotent by content hash), optionally
prune docs whose source ids vanished, and persist the new cursor.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from auralynq.config import get_settings
from auralynq.connectors.base import Connector, ConnectorDoc, ConnectorError
from auralynq.ingest.chunking import chunk_text
from auralynq.ingest.models import Chunk, Document, SourceSpan, SourceType
from auralynq.ingest.pipeline import _Manifest
from auralynq.telemetry import get_logger
from auralynq.utils import stable_id

_log = get_logger("auralynq.connectors")


def _state_path() -> Path:
    return get_settings().storage_dir / "connector_state.json"


def load_state() -> dict[str, dict[str, Any]]:
    p = _state_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state: dict[str, dict[str, Any]]) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _to_document(doc: ConnectorDoc, connector: str) -> Document:
    doc_id = stable_id(doc.source)
    prov = {
        "connector": connector,
        "source": doc.source,
        **({"url": doc.url} if doc.url else {}),
        **doc.metadata,
    }
    chunks: list[Chunk] = []
    for ordinal, tc in enumerate(chunk_text(doc.text)):
        chunks.append(
            Chunk(
                id=Chunk.make_id(doc_id, ordinal),
                doc_id=doc_id,
                text=tc.text,
                ordinal=ordinal,
                span=SourceSpan(start_char=tc.start_char, end_char=tc.end_char, section=tc.section),
                title=doc.title,
                source=doc.source,
                source_type=SourceType.html,
                metadata={
                    "connector": connector,
                    "authored_at": doc.authored_at,
                    "provenance": prov,
                },
            )
        )
    return Document(
        id=doc_id,
        source=doc.source,
        source_type=SourceType.html,
        title=doc.title,
        content_hash=doc.content_hash,
        metadata={"connector": connector, "provenance": prov},
        chunks=chunks,
    )


def sync_connector(connector: Connector, *, force: bool = False) -> dict[str, Any]:
    """Pull changes from one connector, index the new/changed docs, prune deleted
    ones, and persist the cursor. Returns a report dict."""
    report: dict[str, Any] = {
        "connector": connector.name,
        "configured": False,
        "added": 0,
        "updated": 0,
        "removed": 0,
        "unchanged": 0,
        "errors": [],
    }
    if not connector.configured():
        report["errors"].append("not configured — provide the required token/credentials")
        return report
    report["configured"] = True

    s = get_settings()
    s.ensure_dirs()
    state = load_state()
    prior = state.get(connector.name, {})
    cursor = None if force else prior.get("cursor")

    try:
        docs, next_cursor = connector.list_changes(cursor)
    except ConnectorError as exc:
        report["errors"].append(str(exc))
        return report
    except Exception as exc:  # network/parse — non-fatal, reported
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        return report

    manifest = _Manifest(s.storage_dir / "ingest_manifest.json")
    to_index: list[Document] = []
    seen_hashes: dict[str, str] = dict(prior.get("hashes", {}))
    for d in docs:
        prev = seen_hashes.get(d.source)
        if prev == d.content_hash and not force:
            report["unchanged"] += 1
            continue
        report["added" if prev is None else "updated"] += 1
        to_index.append(_to_document(d, connector.name))
        seen_hashes[d.source] = d.content_hash
        manifest.update(d.source, d.content_hash)

    if to_index:
        from auralynq.pipeline import index_documents

        stats = index_documents(to_index)
        manifest.save()
        report["chunks_indexed"] = stats.get("chunks_indexed", 0)

    # Prune docs that no longer exist at the source (best-effort).
    try:
        ids = connector.list_ids()
    except Exception:
        ids = None
    if ids is not None and s.watch.delete_missing:
        from auralynq.serving.corpus_manager import (
            _all_indexed_documents,
            _delete_document_by_id,
        )

        live_sources = {sid for sid in seen_hashes}  # sources we know about
        existing = {sid for sid in ids}
        vanished = {src for src in live_sources if _source_id(src) not in existing}
        if vanished:
            by_source = {d.get("source", ""): d for d in _all_indexed_documents()}
            for src in vanished:
                doc = by_source.get(src)
                if doc and doc.get("doc_id"):
                    try:
                        _delete_document_by_id(str(doc["doc_id"]), doc)
                        report["removed"] += 1
                        seen_hashes.pop(src, None)
                    except Exception as exc:
                        report["errors"].append(f"prune {src}: {exc}")

    import datetime as _dt

    state[connector.name] = {
        "cursor": next_cursor,
        "hashes": seen_hashes,
        "synced_at": _dt.datetime.now(tz=_dt.UTC).isoformat(),
    }
    save_state(state)
    _log.info(
        "connector.synced",
        connector=connector.name,
        added=report["added"],
        updated=report["updated"],
        removed=report["removed"],
    )
    return report


def _source_id(source: str) -> str:
    """Extract the source id from a canonical URI ('notion://<id>' → '<id>')."""
    return source.split("://", 1)[-1] if "://" in source else source
