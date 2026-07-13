"""Build the configured connectors from settings + expose their status."""

from __future__ import annotations

from typing import Any

from auralynq.config import get_settings
from auralynq.connectors.base import Connector
from auralynq.connectors.gdrive import GDriveConnector
from auralynq.connectors.notion import NotionConnector
from auralynq.connectors.slack import SlackConnector


def build_connectors() -> dict[str, Connector]:
    c = get_settings().connectors
    return {
        "notion": NotionConnector(c.notion_token),
        "slack": SlackConnector(c.slack_bot_token),
        "gdrive": GDriveConnector(c.gdrive_credentials_json),
    }


def get_connector(name: str) -> Connector | None:
    return build_connectors().get(name)


def connectors_status() -> list[dict[str, Any]]:
    from auralynq.connectors.sync import load_state

    state = load_state()
    out: list[dict[str, Any]] = []
    for name, conn in build_connectors().items():
        st = state.get(name, {})
        out.append(
            {
                "name": name,
                "configured": conn.configured(),
                "setup_hint": conn.setup_hint(),
                "synced_at": st.get("synced_at"),
                "docs": len(st.get("hashes", {})),
            }
        )
    return out
