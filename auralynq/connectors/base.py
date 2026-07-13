"""Connector framework — pluggable cloud sources (Notion, Slack, Google Drive).

Every connector mirrors the Watch Folder's snapshot→diff→sync loop, but over a
remote **cursor** instead of the filesystem: it reports the documents that
changed since a stored cursor and returns the next cursor. The sync engine
(:mod:`auralynq.connectors.sync`) indexes those docs and persists the cursor,
so a connector re-syncs incrementally on each run — exactly like a watched
folder, generalized to the cloud.

Auth is deliberately single-token / service-account (no hosted OAuth app) so a
local-first user can connect one workspace by pasting one secret. Each connector
declares what the user must provide via :meth:`Connector.setup_hint`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


class ConnectorError(Exception):
    """A connector failure carrying a user-safe message (bad token, rate limit…)."""


@dataclass
class ConnectorDoc:
    """One document pulled from a connector, ready to chunk + index."""

    id: str  # stable id within the source (e.g. Notion page id)
    source: str  # canonical URI used as the citation source, e.g. "notion://<id>"
    title: str
    text: str
    content_hash: str
    authored_at: str | None = None  # ISO8601 — powers cross-source contradiction flags
    url: str | None = None  # human-openable link, when the source has one
    metadata: dict = field(default_factory=dict)


@dataclass
class SyncCursor:
    """Opaque per-connector position marker (Notion last_edited_time, Drive
    pageToken, Slack per-channel ts map, …). Persisted as JSON."""

    value: str | None = None


@runtime_checkable
class Connector(Protocol):
    """A cloud source. Implementations live in this package (notion/slack/gdrive)."""

    name: str  # "notion" | "slack" | "gdrive"

    def configured(self) -> bool:
        """True when the required token/credentials are present."""
        ...

    def setup_hint(self) -> str:
        """One-line, user-facing instruction for what secret to provide."""
        ...

    def list_changes(self, cursor: str | None) -> tuple[list[ConnectorDoc], str | None]:
        """Return documents changed since ``cursor`` and the next cursor.

        On the first run (``cursor is None``) this is a full backfill. Must be
        idempotent: returning an already-seen doc is fine — the index dedupes by
        content hash.
        """
        ...

    def list_ids(self) -> set[str] | None:
        """All currently-existing source ids (for pruning deleted docs), or None
        when the source can't enumerate cheaply."""
        ...
