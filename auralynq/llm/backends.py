"""Availability detection for the local LLM serving backends.

Three backends can serve generation locally, and they fail in different ways, so
"unavailable" is never reported bare — each carries the specific reason and the
remediation. Detection is probe-based and cheap enough to run on a page load:
HTTP for the two server backends, an import + hardware check for AirLLM.

The three differ on axes a single badge cannot express, so the payload keeps them
separate: reachability, hardware requirement, and speed class. AirLLM in
particular *inverts* the ModelFit fit verdict — a model marked too big for the
machine does run under layer streaming, at minutes per answer — so the UI needs
`speed_class` to avoid presenting that as a win.
"""

from __future__ import annotations

import importlib.util
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import httpx

from auralynq.config import get_settings
from auralynq.telemetry import get_logger

_log = get_logger("auralynq.llm.backends")

SpeedClass = Literal["fast", "very_fast", "very_slow"]
Status = Literal["available", "unavailable", "experimental"]

_PROBE_TTL = 15.0
_probe_cache: dict[str, tuple[Any, float]] = {}


def _cached(key: str, fn):
    now = time.monotonic()
    hit = _probe_cache.get(key)
    if hit is not None and now - hit[1] < _PROBE_TTL:
        return hit[0]
    value = fn()
    _probe_cache[key] = (value, now)
    return value


def invalidate_probe_cache() -> None:
    """Force the next detection to re-probe (used by the UI's explicit recheck)."""
    _probe_cache.clear()


@dataclass
class BackendInfo:
    id: str
    name: str
    description: str
    status: Status
    available: bool
    speed_class: SpeedClass
    requires_gpu: bool
    supports_streaming: bool
    detected_at: str | None = None
    version: str | None = None
    models: list[str] = field(default_factory=list)
    active_model: str | None = None
    unavailable_reason: str | None = None
    remediation: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _detect_ollama() -> BackendInfo:
    s = get_settings()
    base = s.llm.base_url.rstrip("/")
    info = BackendInfo(
        id="ollama",
        name="Ollama",
        description="Local daemon that manages, pulls, and serves quantized models.",
        status="unavailable",
        available=False,
        speed_class="fast",
        requires_gpu=False,
        supports_streaming=True,
        detected_at=base,
    )
    try:
        version = httpx.get(f"{base}/api/version", timeout=1.5)
        if version.status_code != 200:
            raise RuntimeError(f"HTTP {version.status_code}")
        info.version = str(version.json().get("version") or "unknown")
        tags = httpx.get(f"{base}/api/tags", timeout=2.0)
        if tags.status_code == 200:
            info.models = [m["name"] for m in tags.json().get("models", []) if m.get("name")]
        info.status = "available"
        info.available = True
        if not info.models:
            info.warnings.append("No models installed yet — pull one from the Models page.")
    except Exception as exc:
        info.unavailable_reason = f"Nothing responding at {base}"
        info.remediation = (
            "Start the daemon with `OLLAMA_HOST=0.0.0.0:11434 ollama serve`. "
            "If Auralynq runs in a container, point AURALYNQ_LLM__BASE_URL at the host."
        )
        _log.debug("backends.ollama_unreachable", base_url=base, error=str(exc))
    return info


def _detect_vllm() -> BackendInfo:
    s = get_settings()
    base = s.llm.vllm_base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {s.llm.vllm_api_key}"} if s.llm.vllm_api_key else {}
    info = BackendInfo(
        id="vllm",
        name="vLLM",
        description=(
            "High-throughput GPU server (OpenAI-compatible). Continuous batching "
            "and PagedAttention — the win shows up under concurrent load."
        ),
        status="unavailable",
        available=False,
        speed_class="very_fast",
        requires_gpu=True,
        supports_streaming=True,
        detected_at=base,
    )
    try:
        resp = httpx.get(f"{base}/models", headers=headers, timeout=1.5)
        if resp.status_code == 401:
            info.unavailable_reason = "vLLM is running but rejected the API key"
            info.remediation = "Set AURALYNQ_LLM__VLLM_API_KEY to match `vllm serve --api-key`."
            return info
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")
        info.models = [str(m["id"]) for m in resp.json().get("data", []) if m.get("id")]
        info.active_model = info.models[0] if info.models else None
        info.status = "available"
        info.available = True
        info.warnings.append(
            "A vLLM process serves one model for its lifetime — switching models "
            "means restarting the server."
        )
    except Exception as exc:
        info.unavailable_reason = f"Nothing responding at {base}"
        info.remediation = (
            "Start a server with `vllm serve <hf-repo-id> --port 8001`, or point "
            "AURALYNQ_LLM__VLLM_BASE_URL at an existing one."
        )
        _log.debug("backends.vllm_unreachable", base_url=base, error=str(exc))
    return info


# AirLLM shards a checkpoint into per-layer files; a 70B needs ~130 GB on disk.
_AIRLLM_DISK_GB = 120.0


def _detect_airllm() -> BackendInfo:
    s = get_settings()
    info = BackendInfo(
        id="airllm",
        name="AirLLM",
        description=(
            "Streams model layers from disk one at a time, so a model far larger "
            "than your VRAM will run. Not for interactive use."
        ),
        status="experimental",
        available=False,
        speed_class="very_slow",
        requires_gpu=False,
        supports_streaming=False,
        active_model=s.llm.airllm_model or None,
        warnings=[
            "Expect 5–40 minutes per answer and 30–60 GB of disk reads each time.",
            "Runs in-process: the machine is largely unusable while it generates.",
        ],
    )

    if importlib.util.find_spec("airllm") is None:
        info.unavailable_reason = "Not installed"
        info.remediation = "pip install airllm (pulls in torch + transformers, ~3 GB)."
        return info

    try:
        from auralynq.modelfit.hardware import probe_hardware

        hw = probe_hardware()
    except Exception:
        hw = None

    if hw is not None:
        if not (hw.cuda_available or hw.metal_available):
            info.unavailable_reason = "No CUDA GPU or Apple Silicon detected"
            info.remediation = "AirLLM needs an accelerator to stream layers into."
            return info
        if hw.disk_free_gb and hw.disk_free_gb < _AIRLLM_DISK_GB:
            info.unavailable_reason = (
                f"Needs ~{_AIRLLM_DISK_GB:.0f} GB free for layer shards; "
                f"{hw.disk_free_gb:.0f} GB available"
            )
            info.remediation = "Free up disk, or use a smaller model."
            return info

    if not s.llm.airllm_enabled:
        info.unavailable_reason = "Installed but not enabled"
        info.remediation = (
            "Set AURALYNQ_LLM__AIRLLM_ENABLED=true to allow it. Kept off by "
            "default because a single answer takes minutes."
        )
        return info

    info.available = True
    return info


_DETECTORS = {
    "ollama": _detect_ollama,
    "vllm": _detect_vllm,
    "airllm": _detect_airllm,
}


def detect_backend(backend_id: str) -> BackendInfo:
    detector = _DETECTORS.get(backend_id)
    if detector is None:
        raise KeyError(backend_id)
    return _cached(f"backend:{backend_id}", detector)


def detect_backends() -> list[BackendInfo]:
    """Probe all three serving backends. Ordered available-first, then by speed."""
    infos = [detect_backend(bid) for bid in _DETECTORS]
    rank = {"very_fast": 0, "fast": 1, "very_slow": 2}
    infos.sort(key=lambda b: (not b.available, rank.get(b.speed_class, 9)))
    return infos


def backends_payload() -> dict[str, Any]:
    from auralynq.llm.factory import resolved_provider

    s = get_settings()
    infos = detect_backends()
    return {
        "backends": [b.to_dict() for b in infos],
        "configured": s.llm.provider,
        "active": resolved_provider(),
        "auto_selected": s.llm.provider == "auto",
    }
