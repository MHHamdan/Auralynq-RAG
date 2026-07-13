"""Slack connector — single **bot token** (xoxb-), no hosted OAuth redirect.

The user creates a Slack app in their workspace, adds scopes (channels:read,
channels:history, groups:history, users:read), installs it, and copies the Bot
User OAuth token into ``AURALYNQ_CONNECTORS__SLACK_BOT_TOKEN`` (a Secret).

Each public channel becomes one indexed document (its recent messages). The
cursor is a per-channel latest-timestamp map.

⚠️ Rate limits: since 2025-05-29, *new non-Marketplace apps* are throttled to
~1 request/minute on conversations.history with page size capped at 15. We keep
requests minimal and index newest-first; a full backfill of a busy workspace can
take many sync cycles. Marketplace-approved apps keep the higher Tier-3 limit.
"""

from __future__ import annotations

import json
import time

from auralynq.connectors.base import ConnectorDoc, ConnectorError
from auralynq.telemetry import get_logger
from auralynq.utils import content_hash

_log = get_logger("auralynq.connectors.slack")
_API = "https://slack.com/api"


class SlackConnector:
    name = "slack"

    def __init__(
        self, token: str, *, max_channels: int = 50, per_channel: int = 200, rate_delay: float = 1.2
    ) -> None:
        self._token = token or ""
        self._max_channels = max_channels
        self._per_channel = per_channel
        self._rate_delay = rate_delay  # bump toward 60s for un-approved apps

    def configured(self) -> bool:
        return self._token.startswith("xox")

    def setup_hint(self) -> str:
        return (
            "Create a Slack app, add channels:history+channels:read scopes, install it, "
            "and set AURALYNQ_CONNECTORS__SLACK_BOT_TOKEN (xoxb-…)."
        )

    def _client(self):
        import httpx

        return httpx.Client(
            base_url=_API, timeout=20.0, headers={"Authorization": f"Bearer {self._token}"}
        )

    def _call(self, client, method: str, params: dict) -> dict:
        time.sleep(self._rate_delay)
        r = client.get(f"/{method}", params=params)
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            err = data.get("error", "unknown_error")
            if err in ("invalid_auth", "not_authed", "token_revoked"):
                raise ConnectorError(f"Slack auth failed ({err}) — check the bot token.")
            if err == "ratelimited":
                raise ConnectorError("Slack rate limit hit — new apps allow ~1 req/min.")
            raise ConnectorError(f"Slack API error: {err}")
        return data

    def _channels(self, client) -> list[dict]:
        out: list[dict] = []
        cursor = None
        while len(out) < self._max_channels:
            params = {"types": "public_channel", "exclude_archived": "true", "limit": 200}
            if cursor:
                params["cursor"] = cursor
            data = self._call(client, "conversations.list", params)
            out.extend(data.get("channels", []))
            cursor = (data.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break
        return out[: self._max_channels]

    def _history(self, client, channel_id: str, oldest: str | None) -> list[dict]:
        params: dict = {"channel": channel_id, "limit": 15}  # capped for un-approved apps
        if oldest:
            params["oldest"] = oldest
        data = self._call(client, "conversations.history", params)
        return data.get("messages", [])

    def list_changes(self, cursor: str | None) -> tuple[list[ConnectorDoc], str | None]:
        if not self.configured():
            raise ConnectorError("Slack bot token not set.")
        try:
            ts_map: dict[str, str] = json.loads(cursor) if cursor else {}
        except Exception:
            ts_map = {}
        docs: list[ConnectorDoc] = []
        with self._client() as client:
            for ch in self._channels(client):
                cid = ch["id"]
                oldest = ts_map.get(cid)
                msgs = self._history(client, cid, oldest)
                if not msgs:
                    continue
                # newest-first from Slack → present oldest-first in the doc
                lines = [m.get("text", "") for m in reversed(msgs) if m.get("text")]
                text = "\n".join(lines).strip()
                if not text:
                    continue
                latest = max((m.get("ts", "0") for m in msgs), default=oldest or "0")
                ts_map[cid] = latest
                docs.append(
                    ConnectorDoc(
                        id=cid,
                        source=f"slack://{cid}",
                        title=f"#{ch.get('name', cid)}",
                        text=text,
                        content_hash=content_hash(text),
                        authored_at=None,
                        url=None,
                        metadata={"channel": ch.get("name"), "latest_ts": latest},
                    )
                )
        _log.info("slack.changes", channels=len(docs))
        return docs, json.dumps(ts_map)

    def list_ids(self) -> set[str] | None:
        if not self.configured():
            return None
        with self._client() as client:
            return {c["id"] for c in self._channels(client)}
