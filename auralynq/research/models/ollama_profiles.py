"""Ollama model profiles + availability detection.

Safety contract (Phase 2 brief):
  * Detect whether Ollama is reachable and list locally-present models.
  * Identify which profile models are *missing* and roughly whether each is
    likely too large for this machine.
  * Provide ``ollama pull`` commands but **never execute them** unless
    ``AURALYNQ_OLLAMA__AUTO_PULL=true`` is explicitly set.

Sizes are approximate (Q4 quantization) and only used for a coarse "fits?" hint.
See ``docs/research/ollama-model-recommendations.md``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx


@dataclass(frozen=True)
class ModelSpec:
    tag: str
    params_b: float  # billions of parameters
    approx_gb: float  # approx on-disk / VRAM footprint at Q4
    role: str = "llm"  # llm | embedding
    note: str = ""


# Profiles intentionally name widely-available tags; code degrades gracefully if a
# tag is absent (it just shows up as "missing").
PROFILES: dict[str, list[ModelSpec]] = {
    "small": [
        ModelSpec("llama3.2:3b", 3.0, 2.0, note="default; good grounding for size"),
        ModelSpec("qwen2.5:3b", 3.0, 2.0, note="strong multilingual"),
        ModelSpec("gemma2:2b", 2.0, 1.6, note="fastest; weaker abstention"),
        ModelSpec("phi3:mini", 3.8, 2.3, note="reasoning-leaning"),
    ],
    "balanced": [
        ModelSpec("llama3.1:8b", 8.0, 4.7, note="strong all-rounder"),
        ModelSpec("mistral:7b", 7.0, 4.1, note="concise"),
        ModelSpec("qwen2.5:7b", 7.0, 4.7, note="multilingual + tables"),
        ModelSpec("gemma2:9b", 9.0, 5.4, note="quality > speed"),
    ],
    "server": [
        ModelSpec("qwen2.5:14b", 14.0, 9.0, note="strong faithfulness"),
        ModelSpec("qwen2.5:32b", 32.0, 20.0, note="server-class"),
        ModelSpec("llama3.3:70b", 70.0, 40.0, note="best quality; heavy"),
        ModelSpec("mixtral:8x7b", 47.0, 26.0, note="MoE throughput"),
    ],
    "embedding": [
        ModelSpec("nomic-embed-text", 0.14, 0.3, role="embedding", note="open default"),
        ModelSpec("mxbai-embed-large", 0.34, 0.7, role="embedding", note="higher dim"),
    ],
}


def _base_url() -> str:
    # Reuse the same env knob the LLM provider uses.
    return os.getenv("AURALYNQ_LLM__BASE_URL", "http://localhost:11434").rstrip("/")


def _total_ram_gb() -> float | None:
    """Best-effort total system RAM in GB (Linux /proc/meminfo)."""
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    kb = float(line.split()[1])
                    return round(kb / (1024 * 1024), 1)
    except OSError:
        return None
    return None


def auto_pull_enabled() -> bool:
    return os.getenv("AURALYNQ_OLLAMA__AUTO_PULL", "false").lower() in ("1", "true", "yes")


@dataclass
class OllamaInventory:
    reachable: bool
    base_url: str
    local_tags: list[str] = field(default_factory=list)
    total_ram_gb: float | None = None
    error: str = ""

    def has(self, tag: str) -> bool:
        # Ollama may report "llama3.2:3b" or with a digest; match on prefix.
        base = tag.split(":")[0]
        return any(t == tag or t.startswith(base + ":") or t == base for t in self.local_tags)

    def likely_fits(self, spec: ModelSpec) -> bool | None:
        """Coarse heuristic: model fits if approx footprint < ~70% of RAM."""
        if self.total_ram_gb is None:
            return None
        return spec.approx_gb < 0.7 * self.total_ram_gb


def inventory(timeout: float = 1.5) -> OllamaInventory:
    """Query Ollama for locally-present models (no pulls)."""
    base = _base_url()
    ram = _total_ram_gb()
    try:
        resp = httpx.get(f"{base}/api/tags", timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        tags = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        return OllamaInventory(reachable=True, base_url=base, local_tags=tags, total_ram_gb=ram)
    except Exception as exc:  # noqa: BLE001 - any failure means "not reachable"
        return OllamaInventory(
            reachable=False, base_url=base, total_ram_gb=ram, error=str(exc)
        )


def list_models_report(inv: OllamaInventory | None = None) -> dict[str, object]:
    """Structured report: per profile, which models are present / missing / fit."""
    inv = inv or inventory()
    profiles: dict[str, list[dict[str, object]]] = {}
    for profile, specs in PROFILES.items():
        rows = []
        for s in specs:
            present = inv.has(s.tag) if inv.reachable else False
            rows.append(
                {
                    "tag": s.tag,
                    "role": s.role,
                    "params_b": s.params_b,
                    "approx_gb": s.approx_gb,
                    "present": present,
                    "likely_fits": inv.likely_fits(s),
                    "pull_cmd": None if present else f"ollama pull {s.tag}",
                    "note": s.note,
                }
            )
        profiles[profile] = rows
    return {
        "reachable": inv.reachable,
        "base_url": inv.base_url,
        "total_ram_gb": inv.total_ram_gb,
        "auto_pull": auto_pull_enabled(),
        "local_tags": inv.local_tags,
        "profiles": profiles,
        "error": inv.error,
    }


def pull_commands(profile: str) -> list[str]:
    """Return (do not run) pull commands for a profile's missing models."""
    inv = inventory()
    cmds: list[str] = []
    for s in PROFILES.get(profile, []):
        if not (inv.reachable and inv.has(s.tag)):
            cmds.append(f"ollama pull {s.tag}")
    return cmds


def ensure_model(tag: str) -> bool:
    """Pull a model **only if** AUTO_PULL is enabled. Returns True if available.

    Never pulls silently; honors the no-auto-download contract.
    """
    inv = inventory()
    if inv.reachable and inv.has(tag):
        return True
    if not auto_pull_enabled():
        return False
    if not inv.reachable:
        return False
    try:
        # Streaming pull; large download — gated behind AUTO_PULL by design.
        with httpx.stream(
            "POST", f"{inv.base_url}/api/pull", json={"name": tag}, timeout=None
        ) as resp:
            for _ in resp.iter_lines():
                pass
        return inventory().has(tag)
    except Exception:  # noqa: BLE001
        return False
