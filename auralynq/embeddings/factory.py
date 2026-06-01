"""Embedder factory with ``auto`` resolution (ADR-0004)."""

from __future__ import annotations

import functools
import importlib.util

from auralynq.config import get_settings
from auralynq.embeddings.base import Embedder
from auralynq.embeddings.hashing import HashingEmbedder
from auralynq.telemetry import get_logger

_log = get_logger("auralynq.embeddings")


def _have(pkg: str) -> bool:
    return importlib.util.find_spec(pkg) is not None


def build_embedder(provider: str | None = None) -> Embedder:
    s = get_settings()
    provider = provider or s.embedding.provider

    if provider == "auto":
        if _have("FlagEmbedding"):
            provider = "bge"
        elif s.openai_api_key and _have("openai"):
            provider = "openai"
        else:
            provider = "hash"

    # Networked/commercial embedders are wrapped so a request-time failure (bad
    # key, inactive billing/429, rate limit, network blip) degrades to the hashing
    # embedder instead of crashing retrieval (ADR-0003).
    fallback_dim = min(s.embedding.dim, 256)
    if provider == "bge":
        try:
            from auralynq.embeddings.bge import BGEM3Embedder
            from auralynq.embeddings.resilient import ResilientEmbedder

            return ResilientEmbedder(
                BGEM3Embedder(
                    model=s.embedding.model, device=s.embedding.device, dim=s.embedding.dim
                ),
                fallback_dim=fallback_dim,
            )
        except Exception as exc:  # pragma: no cover - heavy path
            _log.warning("embeddings.bge_failed_fallback_hash", error=str(exc))
            provider = "hash"

    if provider == "openai":  # pragma: no cover - paid path
        try:
            from auralynq.embeddings.openai_embed import OpenAIEmbedder
            from auralynq.embeddings.resilient import ResilientEmbedder

            return ResilientEmbedder(
                OpenAIEmbedder(api_key=s.openai_api_key), fallback_dim=fallback_dim
            )
        except Exception as exc:
            _log.warning("embeddings.openai_failed_fallback_hash", error=str(exc))
            provider = "hash"

    _log.info("embeddings.using", provider="hash")
    return HashingEmbedder(dim=fallback_dim)


@functools.lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    return build_embedder()


def resolved_provider() -> str:
    s = get_settings()
    if s.embedding.provider != "auto":
        return s.embedding.provider
    if _have("FlagEmbedding"):
        return "bge"
    if s.openai_api_key and _have("openai"):
        return "openai"
    return "hash"
