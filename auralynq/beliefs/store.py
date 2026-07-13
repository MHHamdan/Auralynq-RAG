"""SQLite-backed bi-temporal claim store.

Pure-Python (stdlib ``sqlite3``); no new dependency, no network — fits the
local-first, offline-$0 posture. One table, ``claims``, with two time axes:

    valid_from / valid_to   valid-time  (when the fact holds in the world)
    ingest_time             ingest-time (when we recorded it; monotonic)

Supersession is non-destructive: revising a fact closes the prior claim's
valid-time (``valid_to``) and links it forward (``superseded_by``) — the old row
is never deleted, so ``history`` and ``as_of`` can reconstruct any past belief.
"""

from __future__ import annotations

import datetime as _dt
import functools
import sqlite3
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from auralynq.utils import stable_id


def _now() -> str:
    return _dt.datetime.now(tz=_dt.UTC).isoformat(timespec="seconds")


@dataclass
class Claim:
    """An atomic, provenance-carrying, bi-temporal assertion."""

    claim_id: str
    entity: str
    predicate: str
    object: str
    source: str = ""
    doc_id: str = ""
    valid_from: str = ""  # ISO-8601; valid-time start
    valid_to: str | None = None  # ISO-8601; valid-time end (None = still holds)
    ingest_time: str = ""  # ISO-8601; when recorded (transaction-time)
    superseded_by: str | None = None  # claim_id that replaced this one
    confidence: float = 1.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
    claim_id      TEXT PRIMARY KEY,
    entity        TEXT NOT NULL,
    predicate     TEXT NOT NULL,
    object        TEXT NOT NULL,
    source        TEXT NOT NULL DEFAULT '',
    doc_id        TEXT NOT NULL DEFAULT '',
    valid_from    TEXT NOT NULL DEFAULT '',
    valid_to      TEXT,
    ingest_time   TEXT NOT NULL DEFAULT '',
    superseded_by TEXT,
    confidence    REAL NOT NULL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS idx_claims_entity ON claims(entity);
CREATE INDEX IF NOT EXISTS idx_claims_ep ON claims(entity, predicate);
"""

_COLS = (
    "claim_id, entity, predicate, object, source, doc_id, "
    "valid_from, valid_to, ingest_time, superseded_by, confidence"
)


class BeliefStore:
    """A bi-temporal store of claims. Safe to share across threads."""

    def __init__(self, db_path: Path | str) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # check_same_thread=False + our own lock: the FastAPI server touches this
        # from worker threads, but every write goes through the lock below.
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(_SCHEMA)

    # -------------------------------------------------------------- write ---
    def record_claim(
        self,
        entity: str,
        predicate: str,
        object: str,
        *,
        source: str = "",
        doc_id: str = "",
        valid_from: str | None = None,
        ingest_time: str | None = None,
        confidence: float = 1.0,
    ) -> str:
        """Insert a new open-ended claim (``valid_to`` = None) and return its id.

        The id is deterministic over (entity, predicate, object, source, doc_id)
        so re-recording the same assertion from the same source is idempotent.
        """
        entity = entity.strip()
        predicate = predicate.strip()
        object = object.strip()
        now = _now()
        vf = valid_from or now
        it = ingest_time or now
        claim_id = stable_id("claim", entity.lower(), predicate.lower(), object.lower(), source)
        with self._lock, self._conn:
            self._conn.execute(
                f"INSERT OR REPLACE INTO claims ({_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    claim_id,
                    entity,
                    predicate,
                    object,
                    source,
                    doc_id,
                    vf,
                    None,
                    it,
                    None,
                    confidence,
                ),
            )
        return claim_id

    def supersede(self, old_claim_id: str, new_claim_id: str, *, at: str | None = None) -> bool:
        """Close a prior claim's valid-time and link it to its replacement.

        ``at`` is the valid-time instant the old fact stopped holding (defaults
        to now). Returns False if ``old_claim_id`` is unknown.
        """
        at = at or _now()
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE claims SET valid_to = ?, superseded_by = ? "
                "WHERE claim_id = ? AND superseded_by IS NULL",
                (at, new_claim_id, old_claim_id),
            )
            return cur.rowcount > 0

    def revise(
        self,
        entity: str,
        predicate: str,
        object: str,
        *,
        source: str = "",
        doc_id: str = "",
        valid_from: str | None = None,
        confidence: float = 1.0,
    ) -> str:
        """Record a new value for (entity, predicate), superseding the current
        open claim(s) for that pair whose object differs. Returns the new id.

        This is the convenience path the ingest layer uses: it makes belief
        revision one call while preserving the full history.
        """
        now = _now()
        vf = valid_from or now
        new_id = self.record_claim(
            entity,
            predicate,
            object,
            source=source,
            doc_id=doc_id,
            valid_from=vf,
            confidence=confidence,
        )
        obj_norm = object.strip().lower()
        for prior in self._open_claims(entity, predicate):
            if prior.claim_id != new_id and prior.object.strip().lower() != obj_norm:
                self.supersede(prior.claim_id, new_id, at=vf)
        return new_id

    # --------------------------------------------------------------- read ---
    def get(self, claim_id: str) -> Claim | None:
        row = self._conn.execute(
            f"SELECT {_COLS} FROM claims WHERE claim_id = ?", (claim_id,)
        ).fetchone()
        return _row_to_claim(row) if row else None

    def history(self, entity: str) -> list[Claim]:
        """All claims about an entity, oldest valid-time first (revision order)."""
        rows = self._conn.execute(
            f"SELECT {_COLS} FROM claims WHERE entity = ? ORDER BY valid_from ASC, ingest_time ASC",
            (entity.strip(),),
        ).fetchall()
        return [_row_to_claim(r) for r in rows]

    def as_of(self, entity: str, valid_time: str, *, ingest_time: str | None = None) -> list[Claim]:
        """Claims believed true for ``entity`` at a given valid-time instant.

        Bi-temporal time travel: pass ``ingest_time`` to also constrain to what
        the system knew as of that transaction-time ("what did we believe, as of
        when"). A claim matches when its valid-time interval contains
        ``valid_time`` and — if given — it was recorded on or before
        ``ingest_time``.
        """
        sql = (
            f"SELECT {_COLS} FROM claims WHERE entity = ? "
            "AND valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)"
        )
        params: list[str] = [entity.strip(), valid_time, valid_time]
        if ingest_time is not None:
            sql += " AND ingest_time <= ?"
            params.append(ingest_time)
        sql += " ORDER BY valid_from ASC"
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_claim(r) for r in rows]

    def current(self, entity: str) -> list[Claim]:
        """Claims that still hold now (open valid-time, not superseded)."""
        rows = self._conn.execute(
            f"SELECT {_COLS} FROM claims WHERE entity = ? "
            "AND valid_to IS NULL AND superseded_by IS NULL "
            "ORDER BY valid_from ASC",
            (entity.strip(),),
        ).fetchall()
        return [_row_to_claim(r) for r in rows]

    def entities(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT entity FROM claims ORDER BY entity ASC"
        ).fetchall()
        return [r["entity"] for r in rows]

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0])

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------ private ---
    def _open_claims(self, entity: str, predicate: str) -> list[Claim]:
        rows = self._conn.execute(
            f"SELECT {_COLS} FROM claims WHERE entity = ? AND predicate = ? "
            "AND valid_to IS NULL AND superseded_by IS NULL",
            (entity.strip(), predicate.strip()),
        ).fetchall()
        return [_row_to_claim(r) for r in rows]


def _row_to_claim(row: sqlite3.Row) -> Claim:
    return Claim(
        claim_id=row["claim_id"],
        entity=row["entity"],
        predicate=row["predicate"],
        object=row["object"],
        source=row["source"],
        doc_id=row["doc_id"],
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        ingest_time=row["ingest_time"],
        superseded_by=row["superseded_by"],
        confidence=row["confidence"],
    )


@functools.lru_cache(maxsize=8)
def _store_for(path: str) -> BeliefStore:
    return BeliefStore(path)


def get_belief_store(db_path: Path | str | None = None) -> BeliefStore:
    """Return a process-cached :class:`BeliefStore` for ``db_path``.

    Defaults to ``settings.beliefs_db``. Cached per path so the server reuses a
    single connection instead of reopening the database per request.
    """
    if db_path is None:
        from auralynq.config.settings import get_settings

        db_path = get_settings().beliefs_db
    return _store_for(str(db_path))
