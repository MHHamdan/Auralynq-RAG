"""Ollama REST client for ModelFit.

ModelFit used to shell out to the `ollama` CLI and hardcode `localhost:11434`.
Neither works inside the API container: the binary is not in the image (pull
failed with `[Errno 2] No such file or directory`) and `localhost` is the
container itself, not the host running the Ollama daemon.

Everything here speaks the HTTP API and resolves the base URL from settings, so
a containerised API talks to whatever `AURALYNQ_LLM__BASE_URL` points at.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from auralynq.telemetry import get_logger

_log = get_logger("auralynq.modelfit.ollama")

# A single layer can take minutes between NDJSON frames on a slow link, so the
# read timeout on a pull must be unbounded — connect/write stay short.
_PULL_TIMEOUT = httpx.Timeout(connect=5.0, read=None, write=10.0, pool=None)


def ollama_base_url() -> str:
    """Resolve the Ollama endpoint: modelfit override, else the shared LLM one."""
    from auralynq.config.settings import get_settings

    s = get_settings()
    url = (getattr(s.modelfit, "ollama_url", "") or "").strip() or s.llm.base_url
    return url.rstrip("/")


class OllamaUnreachable(RuntimeError):
    """The Ollama daemon did not answer at the configured base URL."""

    def __init__(self, base_url: str, cause: Exception | None = None) -> None:
        self.base_url = base_url
        self.cause = cause
        super().__init__(
            f"Ollama is not reachable at {base_url}. Start it with "
            f"`OLLAMA_HOST=0.0.0.0:11434 ollama serve`, and if Auralynq runs in a "
            f"container make sure AURALYNQ_LLM__BASE_URL points at the host."
        )


def probe_version_sync(timeout: float = 1.5) -> tuple[bool, str | None]:
    """Blocking availability probe. Used by the sync hardware profiler."""
    base = ollama_base_url()
    try:
        r = httpx.get(f"{base}/api/version", timeout=timeout)
        if r.status_code != 200:
            return False, None
        return True, str(r.json().get("version") or "unknown")
    except Exception:
        return False, None


async def get_version(timeout: float = 3.0) -> str | None:
    base = ollama_base_url()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(f"{base}/api/version")
            if r.status_code != 200:
                return None
            return str(r.json().get("version") or "unknown")
    except Exception:
        return None


async def list_tags(timeout: float = 3.0) -> list[dict[str, Any]]:
    """Installed models. Returns [] when Ollama is unreachable."""
    base = ollama_base_url()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(f"{base}/api/tags")
            if r.status_code != 200:
                return []
            models = r.json().get("models", [])
            return models if isinstance(models, list) else []
    except Exception:
        return []


async def show(tag: str, timeout: float = 5.0) -> dict[str, Any] | None:
    """Model metadata (`/api/show`). Returns None when unavailable."""
    base = ollama_base_url()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(f"{base}/api/show", json={"model": tag})
            if r.status_code != 200:
                return None
            payload = r.json()
            return payload if isinstance(payload, dict) else None
    except Exception:
        return None


async def delete(tag: str, timeout: float = 30.0) -> tuple[bool, str]:
    """Remove an installed model."""
    base = ollama_base_url()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.request("DELETE", f"{base}/api/delete", json={"model": tag})
            if r.status_code in (200, 204):
                return True, f"Deleted {tag}."
            return False, (r.text or f"HTTP {r.status_code}")[:400]
    except httpx.ConnectError as exc:
        raise OllamaUnreachable(base, exc) from exc
    except Exception as exc:  # pragma: no cover - defensive
        return False, str(exc)[:400]


async def stream_pull(tag: str) -> AsyncIterator[dict[str, Any]]:
    """Yield raw NDJSON frames from `POST /api/pull`.

    Ollama reports most pull failures as `{"error": ...}` inside a 200 response,
    so callers must inspect every frame rather than trusting the status code.
    """
    base = ollama_base_url()
    url = f"{base}/api/pull"
    payload = {"model": tag, "stream": True}
    try:
        async with (
            httpx.AsyncClient(timeout=_PULL_TIMEOUT) as client,
            client.stream("POST", url, json=payload) as resp,
        ):
            if resp.status_code != 200:
                body = (await resp.aread()).decode("utf-8", "replace")
                yield {"error": body[:400] or f"HTTP {resp.status_code}"}
                return
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                try:
                    frame = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(frame, dict):
                    yield frame
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise OllamaUnreachable(base, exc) from exc


# ── Error classification ───────────────────────────────────────────────────────

# Maps a substring of Ollama's error text to (http_status, human message).
_ERROR_RULES: tuple[tuple[tuple[str, ...], int, str], ...] = (
    (
        ("no space left", "enospc", "not enough space"),
        507,
        "Not enough disk space to download {tag}. Free up space and retry.",
    ),
    (
        ("unauthorized", "authentication", "403"),
        403,
        "Access to {tag} is restricted — it may be a private or gated model.",
    ),
    (
        ("file does not exist", "manifest unknown", "pull model manifest", "not found", "404"),
        404,
        "Model '{tag}' was not found in the Ollama registry. Check the exact tag name.",
    ),
    (
        ("connection refused", "connection reset", "timeout", "eof", "network"),
        502,
        "The download of {tag} hit a network error. Retry — Ollama resumes partial downloads.",
    ),
)


def classify_pull_error(tag: str, raw: str) -> tuple[int, str]:
    """Map an Ollama error string to an HTTP status and an actionable message."""
    low = (raw or "").lower()
    for needles, status, template in _ERROR_RULES:
        if any(n in low for n in needles):
            return status, template.format(tag=tag)
    return 500, f"Pull of {tag} failed: {(raw or 'unknown error')[:400]}"
