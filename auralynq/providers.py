"""Single source of truth for 'what is actually running' (ADR-0004).

Resolves every swappable backend to its concrete provider and reports status, so
``/health`` and ``auralynq info`` are honest about local-vs-upgraded execution.
"""

from __future__ import annotations

from typing import Any

from auralynq.config import get_settings


def describe_providers() -> list[dict[str, str]]:
    from auralynq.embeddings.factory import resolved_provider as emb_provider
    from auralynq.llm.factory import resolved_provider as llm_provider
    from auralynq.telemetry.langfuse_export import langfuse_enabled
    from auralynq.vectorstore.factory import resolved_backend as vec_backend
    from auralynq.voice.factory import resolved_asr, resolved_tts

    s = get_settings()
    tracing = "langfuse+phoenix" if langfuse_enabled() else "in-process"
    rows = [
        ("embeddings", emb_provider(), "model=" + s.embedding.model),
        ("vector_store", vec_backend(), "url=" + s.vector.url),
        ("rerank", _rerank_provider(), "model=" + s.rerank.model),
        ("llm", llm_provider(), "model=" + s.llm.model),
        ("asr", resolved_asr(), "model=" + s.voice.asr_model),
        ("tts", resolved_tts(), "voice=" + s.voice.tts_voice),
        ("tracing", tracing, "host=" + s.telemetry.langfuse_host),
    ]
    return [{"subsystem": name, "provider": prov, "status": status} for name, prov, status in rows]


def _rerank_provider() -> str:
    import importlib.util

    s = get_settings()
    if s.rerank.provider != "auto":
        return s.rerank.provider
    if s.cohere_api_key and importlib.util.find_spec("cohere"):
        return "cohere"
    if importlib.util.find_spec("FlagEmbedding"):
        return "bge"
    return "lexical"


def health_snapshot() -> dict[str, Any]:
    s = get_settings()
    return {
        "status": "ok",
        "version": __import__("auralynq").__version__,
        "env": s.env,
        "providers": describe_providers(),
        "hf_token_present": bool(s.huggingface_token),
    }
