"""LLM factory with ``auto`` resolution + extractive fallback."""

from __future__ import annotations

import functools
import importlib.util

import httpx

from auralynq.config import get_settings
from auralynq.llm.base import LLM
from auralynq.llm.fallback import ExtractiveLLM
from auralynq.telemetry import get_logger

_log = get_logger("auralynq.llm")


def _ollama_reachable(base_url: str) -> bool:
    try:  # pragma: no cover - network probe
        httpx.get(base_url.rstrip("/") + "/api/tags", timeout=0.5)
        return True
    except Exception:
        return False


# Sensible per-provider default models. The global default (llama3.2:3b) targets
# Ollama; if the resolved provider is a commercial API and the configured model
# still looks like an Ollama tag, fall back to that provider's default so an
# OPENAI/ANTHROPIC key doesn't 404 on a local model name.
_PROVIDER_DEFAULT_MODEL = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-latest",
    "cohere": "command-r-08-2024",
}
_OLLAMA_MODEL_HINTS = ("llama", "qwen", "mistral", "gemma", "phi", "deepseek", ":")


def _model_for(provider: str, configured: str) -> str:
    default = _PROVIDER_DEFAULT_MODEL.get(provider)
    if default is None:
        return configured
    looks_like_ollama = any(h in configured.lower() for h in _OLLAMA_MODEL_HINTS)
    if looks_like_ollama:
        _log.info("llm.model_defaulted", provider=provider, model=default, ignored=configured)
        return default
    return configured


def build_llm(provider: str | None = None) -> LLM:
    s = get_settings()
    provider = provider or s.llm.provider

    if provider == "auto":
        if s.anthropic_api_key and importlib.util.find_spec("anthropic"):
            provider = "anthropic"
        elif s.openai_api_key and importlib.util.find_spec("openai"):
            provider = "openai"
        elif s.cohere_api_key and importlib.util.find_spec("cohere"):
            provider = "cohere"
        elif _ollama_reachable(s.llm.base_url):
            provider = "ollama"
        else:
            provider = "extractive"

    # Networked/commercial providers are wrapped so a request-time failure (bad
    # key, inactive billing, rate limit, network blip) degrades to extractive
    # instead of 500-ing the query (ADR-0003).
    try:
        if provider == "ollama":
            from auralynq.llm.providers import OllamaLLM
            from auralynq.llm.resilient import ResilientLLM

            return ResilientLLM(OllamaLLM(s.llm.model, s.llm.base_url))
        if provider == "openai":
            from auralynq.llm.providers import OpenAILLM
            from auralynq.llm.resilient import ResilientLLM

            return ResilientLLM(OpenAILLM(s.openai_api_key, _model_for("openai", s.llm.model)))
        if provider == "anthropic":
            from auralynq.llm.providers import AnthropicLLM
            from auralynq.llm.resilient import ResilientLLM

            return ResilientLLM(
                AnthropicLLM(s.anthropic_api_key, _model_for("anthropic", s.llm.model))
            )
        if provider == "cohere":
            from auralynq.llm.providers import CohereLLM
            from auralynq.llm.resilient import ResilientLLM

            return ResilientLLM(CohereLLM(s.cohere_api_key, _model_for("cohere", s.llm.model)))
    except Exception as exc:  # construction failure (e.g. missing sdk) → extractive
        _log.warning("llm.fallback_extractive", error=str(exc))

    _log.info("llm.using", provider="extractive")
    return ExtractiveLLM()


def resolved_provider() -> str:
    s = get_settings()
    if s.llm.provider != "auto":
        return s.llm.provider
    if s.anthropic_api_key and importlib.util.find_spec("anthropic"):
        return "anthropic"
    if s.openai_api_key and importlib.util.find_spec("openai"):
        return "openai"
    if s.cohere_api_key and importlib.util.find_spec("cohere"):
        return "cohere"
    if _ollama_reachable(s.llm.base_url):
        return "ollama"
    return "extractive"


@functools.lru_cache(maxsize=1)
def get_llm() -> LLM:
    return build_llm()
