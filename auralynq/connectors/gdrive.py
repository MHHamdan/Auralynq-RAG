"""Google Drive connector — **service-account** credentials, no interactive OAuth.

The user creates a service account, downloads its JSON key, and shares the
folders/files they want indexed with the service account's email. Set
``AURALYNQ_CONNECTORS__GDRIVE_CREDENTIALS_JSON`` to the JSON key (inline or a
path). The incremental cursor is Drive's changes ``pageToken`` (never expires).

Requires the ``connectors`` extra (google-api-python-client + google-auth); the
import is guarded so the rest of Auralynq runs without it.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from auralynq.connectors.base import ConnectorDoc, ConnectorError
from auralynq.telemetry import get_logger
from auralynq.utils import content_hash

_log = get_logger("auralynq.connectors.gdrive")

_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
# Google-native types → export MIME. Others are downloaded as-is when text.
_EXPORT = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.presentation": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
}


def _sdk_available() -> bool:
    return bool(importlib.util.find_spec("googleapiclient")) and bool(
        importlib.util.find_spec("google.oauth2")
    )


class GDriveConnector:
    name = "gdrive"

    def __init__(self, credentials_json: str, *, max_files: int = 200) -> None:
        self._creds_raw = credentials_json or ""
        self._max_files = max_files

    def configured(self) -> bool:
        return bool(self._creds_raw) and _sdk_available()

    def setup_hint(self) -> str:
        if self._creds_raw and not _sdk_available():
            return "Install the 'connectors' extra: pip install -e '.[connectors]'."
        return (
            "Create a service account, share your Drive folders with its email, and set "
            "AURALYNQ_CONNECTORS__GDRIVE_CREDENTIALS_JSON (the JSON key, inline or a path)."
        )

    # Overridable for tests: return a Drive API service object.
    def _service(self):
        from google.oauth2 import service_account  # type: ignore[import-untyped]
        from googleapiclient.discovery import build  # type: ignore[import-untyped]

        raw = self._creds_raw.strip()
        info = (
            json.loads(Path(raw).read_text())
            if raw.endswith(".json") and Path(raw).exists()
            else json.loads(raw)
        )
        creds = service_account.Credentials.from_service_account_info(info, scopes=_SCOPES)
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    def _download_text(self, service, file: dict) -> str:
        mime = file.get("mimeType", "")
        fid = file["id"]
        try:
            if mime in _EXPORT:
                data = service.files().export(fileId=fid, mimeType=_EXPORT[mime]).execute()
            elif mime.startswith("text/") or mime in ("application/json",):
                data = service.files().get_media(fileId=fid).execute()
            else:
                return ""  # skip binaries (PDF path could render later)
            return data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data)
        except Exception as exc:  # one bad file must not abort the sync
            _log.warning("gdrive.download_failed", file=fid, error=str(exc))
            return ""

    def list_changes(self, cursor: str | None) -> tuple[list[ConnectorDoc], str | None]:
        if not self.configured():
            raise ConnectorError("Google Drive credentials not set or SDK missing.")
        try:
            service = self._service()
        except Exception as exc:
            raise ConnectorError(f"Google Drive auth failed: {exc}") from exc

        fields_file = "id,name,mimeType,modifiedTime,webViewLink"
        docs: list[ConnectorDoc] = []
        if not cursor:
            # Full backfill: enumerate readable files.
            resp = (
                service.files()
                .list(
                    pageSize=min(self._max_files, 1000),
                    fields=f"files({fields_file})",
                    q="trashed=false",
                )
                .execute()
            )
            files = resp.get("files", [])
            token = service.changes().getStartPageToken().execute().get("startPageToken")
        else:
            # Incremental: only changed files since the cursor.
            resp = (
                service.changes()
                .list(pageToken=cursor, fields=f"newStartPageToken,changes(file({fields_file}))")
                .execute()
            )
            files = [c["file"] for c in resp.get("changes", []) if c.get("file")]
            token = resp.get("newStartPageToken") or cursor

        for f in files[: self._max_files]:
            text = self._download_text(service, f)
            if not text.strip():
                continue
            docs.append(
                ConnectorDoc(
                    id=f["id"],
                    source=f"gdrive://{f['id']}",
                    title=f.get("name", f["id"]),
                    text=text,
                    content_hash=content_hash(text),
                    authored_at=f.get("modifiedTime"),
                    url=f.get("webViewLink"),
                    metadata={"mimeType": f.get("mimeType")},
                )
            )
        _log.info("gdrive.changes", count=len(docs))
        return docs, token

    def list_ids(self) -> set[str] | None:
        return None  # enumerating all Drive ids each sync is too costly; skip pruning
