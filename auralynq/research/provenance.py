"""Run provenance capture — reproducibility without secrets.

Records git commit, config snapshot, dataset id, model/provider/embedder,
retrieval mode, hardware summary, seed, env-var *names* (values redacted),
timestamp and duration. A test asserts no secret-looking values leak here.
"""

from __future__ import annotations

import os
import platform
import subprocess
from typing import Any

# Env-var name fragments whose *values* must never be recorded.
_SECRET_HINTS = ("key", "token", "secret", "password", "passwd", "credential")


def _git_commit() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


def _git_dirty() -> bool:
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain"], stderr=subprocess.DEVNULL
        ).decode()
        return bool(out.strip())
    except Exception:
        return False


def _hardware() -> dict[str, Any]:
    info: dict[str, Any] = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "processor": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
    }
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    info["mem_total_gb"] = round(float(line.split()[1]) / (1024 * 1024), 1)
                    break
    except OSError:
        pass
    return info


def redacted_env_names(prefixes: tuple[str, ...] = ("AURALYNQ_",)) -> dict[str, str]:
    """Return relevant env-var **names** with redacted values.

    Secret-looking vars are reported as present/absent only; non-secret AURALYNQ_*
    config vars keep their (non-sensitive) values for reproducibility.
    """
    out: dict[str, str] = {}
    for name, value in sorted(os.environ.items()):
        if not name.startswith(prefixes):
            continue
        if any(h in name.lower() for h in _SECRET_HINTS):
            out[name] = "<redacted:present>" if value else "<redacted:empty>"
        else:
            out[name] = value
    # Also note whether well-known secrets are configured, without values.
    for sk in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "COHERE_API_KEY", "HUGGINGFACE_TOKEN"):
        out[sk] = "<redacted:present>" if os.getenv(sk) else "<redacted:absent>"
    return out


def build_provenance(
    *,
    config: dict[str, Any],
    dataset: str,
    n_examples: int,
    started_iso: str,
    duration_s: float,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the provenance record for a run (no secrets)."""
    prov: dict[str, Any] = {
        "git_commit": _git_commit(),
        "git_dirty": _git_dirty(),
        "config": config,
        "dataset": dataset,
        "n_examples": n_examples,
        "seed": int(os.getenv("AURALYNQ_SEED", config.get("seed", 42))),
        "hardware": _hardware(),
        "env": redacted_env_names(),
        "timestamp": started_iso,
        "duration_s": round(duration_s, 3),
    }
    if extra:
        prov.update(extra)
    return prov
