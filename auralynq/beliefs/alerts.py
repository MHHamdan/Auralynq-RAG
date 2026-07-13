"""Proactive contradiction alerts (S2).

When a newly-synced document overturns a prior belief, the compounding wiki
already *detects* the contradiction (``wiki/contradiction.py``). This module
turns that detection into a **proactive, queryable alert** — "this contradicts
your Q3 policy" — instead of a line buried in the wiki log.

Append-only JSONL (mirrors ``WikiStore``'s ``_log.jsonl`` convention) under
``storage_dir/alerts.jsonl``; no new dependency. Alerts are advisory and
idempotent (stable id per entity + claim pair), so re-syncing the same
conflicting source never double-fires.
"""

from __future__ import annotations

import functools
import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import orjson

from auralynq.utils import stable_id


def _alert_id(entity: str, old_claim: str, new_claim: str) -> str:
    return stable_id("alert", entity.lower(), old_claim.lower(), new_claim.lower())


@dataclass
class Alert:
    """A surfaced belief contradiction awaiting the user's attention."""

    id: str
    entity: str
    old_claim: str
    new_claim: str
    why: str = ""
    source: str = ""  # the doc/source that introduced the conflicting claim
    flagged_at: str = ""
    read: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class AlertStore:
    """Append-only store of contradiction alerts, safe across threads."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # -------------------------------------------------------------- write ---
    def emit(self, alerts: list[Alert]) -> int:
        """Append new alerts, skipping ids already present. Returns the number
        actually written (idempotent)."""
        if not alerts:
            return 0
        with self._lock:
            seen = {a.id for a in self._read_all()}
            written = 0
            with self.path.open("ab") as fh:
                for a in alerts:
                    if a.id in seen:
                        continue
                    fh.write(orjson.dumps(a.as_dict()) + b"\n")
                    seen.add(a.id)
                    written += 1
            return written

    def emit_contradictions(self, contradictions: list[dict[str, Any]], *, source: str = "") -> int:
        """Convenience: map ``Contradiction.to_dict()`` records to alerts and emit."""
        alerts = [
            Alert(
                id=_alert_id(c.get("entity", ""), c.get("old_claim", ""), c.get("new_claim", "")),
                entity=c.get("entity", ""),
                old_claim=c.get("old_claim", ""),
                new_claim=c.get("new_claim", ""),
                why=c.get("why", ""),
                source=source,
                flagged_at=c.get("flagged_at", ""),
            )
            for c in contradictions
        ]
        return self.emit(alerts)

    def mark_read(self, ids: list[str] | None = None) -> int:
        """Mark the given alert ids read (or all when ``ids`` is None). Returns
        how many transitioned from unread to read."""
        with self._lock:
            rows = self._read_all()
            target = set(ids) if ids is not None else None
            changed = 0
            for a in rows:
                if (target is None or a.id in target) and not a.read:
                    a.read = True
                    changed += 1
            if changed:
                self._rewrite(rows)
            return changed

    # --------------------------------------------------------------- read ---
    def list_alerts(self, *, unread_only: bool = False) -> list[Alert]:
        rows = self._read_all()
        if unread_only:
            rows = [a for a in rows if not a.read]
        # Newest first (append order is oldest→newest).
        return list(reversed(rows))

    def unread_count(self) -> int:
        return sum(1 for a in self._read_all() if not a.read)

    # ------------------------------------------------------------ private ---
    def _read_all(self) -> list[Alert]:
        if not self.path.exists():
            return []
        out: list[Alert] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                out.append(
                    Alert(
                        id=d.get("id", ""),
                        entity=d.get("entity", ""),
                        old_claim=d.get("old_claim", ""),
                        new_claim=d.get("new_claim", ""),
                        why=d.get("why", ""),
                        source=d.get("source", ""),
                        flagged_at=d.get("flagged_at", ""),
                        read=bool(d.get("read", False)),
                    )
                )
        return out

    def _rewrite(self, rows: list[Alert]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("wb") as fh:
            for a in rows:
                fh.write(orjson.dumps(a.as_dict()) + b"\n")
        tmp.replace(self.path)


@functools.lru_cache(maxsize=8)
def _store_for(path: str) -> AlertStore:
    return AlertStore(path)


def get_alert_store(path: Path | str | None = None) -> AlertStore:
    """Return a process-cached :class:`AlertStore`. Defaults to
    ``settings.storage_dir/alerts.jsonl``."""
    if path is None:
        from auralynq.config.settings import get_settings

        path = get_settings().storage_dir / "alerts.jsonl"
    return _store_for(str(path))
