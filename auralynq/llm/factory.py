"""LLM factory with ``auto`` resolution + extractive fallback.

Auto-resolution priority (local-first, zero-cost):
  1. vllm     — if a local vLLM server answers (GPU, batched, OpenAI-compatible)
  2. ollama   — if daemon is reachable (GPU/CPU handled by Ollama)
  3. slm      — llama-cpp-python GGUF (GPU when CUDA present, CPU otherwise)
  4. anthropic — if ANTHROPIC_API_KEY set and SDK installed
  5. openai   — if OPENAI_API_KEY set and SDK installed
  6. cohere   — if COHERE_API_KEY set and SDK installed
  7. extractive — citation-faithful quotation (always available, no generation)

`airllm` is never auto-selected: it runs a model far larger than the machine's
VRAM by streaming layers from disk, at minutes per answer. Explicit choice only.

Hosted providers (huggingface/openai/anthropic/cohere) are never auto-selected and
are wrapped so a request-time failure degrades down a chain: hosted → local Ollama
→ local GGUF SLM → extractive. See :mod:`auralynq.llm.resilient`.
"""

from __future__ import annotations

import functools
import importlib.util
import time

import httpx

from auralynq.config import get_settings
from auralynq.llm.base import LLM
from auralynq.llm.fallback import ExtractiveLLM
from auralynq.telemetry import get_logger

_log = get_logger("auralynq.llm")

# TTL cache for the Ollama reachability probe: resolved_provider() runs on every
# /health and provider-resolution call, and a blocking 0.5s probe per hit adds up.
_OLLAMA_PROBE_TTL = 30.0
_ollama_probe: dict[str, tuple[bool, float]] = {}


def _ollama_reachable(base_url: str) -> bool:
    now = time.monotonic()
    cached = _ollama_probe.get(base_url)
    if cached is not None and now - cached[1] < _OLLAMA_PROBE_TTL:
        return cached[0]
    try:  # pragma: no cover - network probe
        httpx.get(base_url.rstrip("/") + "/api/tags", timeout=0.5)
        ok = True
    except Exception:
        ok = False
    _ollama_probe[base_url] = (ok, now)
    return ok


_vllm_probe: dict[str, tuple[bool, float]] = {}


def _vllm_reachable(base_url: str) -> bool:
    """True when a vLLM server answers on its OpenAI-compatible route."""
    now = time.monotonic()
    cached = _vllm_probe.get(base_url)
    if cached is not None and now - cached[1] < _OLLAMA_PROBE_TTL:
        return cached[0]
    try:  # pragma: no cover - network probe
        resp = httpx.get(base_url.rstrip("/") + "/models", timeout=0.5)
        ok = resp.status_code == 200
    except Exception:
        ok = False
    _vllm_probe[base_url] = (ok, now)
    return ok


def _slm_available() -> bool:
    """True when llama-cpp-python is installed (model is resolved lazily)."""
    return importlib.util.find_spec("llama_cpp") is not None


# Sensible per-provider default models. The global default (llama3.2:3b) targets
# Ollama; if the resolved provider is a commercial API and the configured model
# still looks like an Ollama tag, fall back to that provider's default so an
# OPENAI/ANTHROPIC key doesn't 404 on a local model name.
_PROVIDER_DEFAULT_MODEL = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-latest",
    "cohere": "command-r-08-2024",
    # HF Inference Providers — a strong, broadly-available default for PRO accounts.
    "huggingface": "meta-llama/Llama-3.3-70B-Instruct",
}
_OLLAMA_MODEL_HINTS = ("llama", "qwen", "mistral", "gemma", "phi", "deepseek", ":")
# Preferred local generation model when falling back from a hosted provider.
_OLLAMA_DEFAULT_MODEL = "llama3.2:3b"
# Embedding-only tags are never valid generation backups.
_EMBED_HINTS = ("embed", "bge-m3")


def _model_for(provider: str, configured: str) -> str:
    default = _PROVIDER_DEFAULT_MODEL.get(provider)
    if default is None:
        return configured
    # HF model ids are repo paths ("org/model") and legitimately contain the
    # ollama-ish substrings above — trust any "/"-shaped id, else use the default.
    if provider == "huggingface":
        return configured if "/" in configured else default
    looks_like_ollama = any(h in configured.lower() for h in _OLLAMA_MODEL_HINTS)
    if looks_like_ollama:
        _log.info("llm.model_defaulted", provider=provider, model=default, ignored=configured)
        return default
    return configured


def _installed_ollama_models(base_url: str) -> list[str]:
    try:  # pragma: no cover - network probe
        resp = httpx.get(base_url.rstrip("/") + "/api/tags", timeout=1.0)
        return [m["name"] for m in resp.json().get("models", []) if m.get("name")]
    except Exception:
        return []


def _ollama_backup_model(configured: str, base_url: str) -> str | None:
    """Pick a generation model that the Ollama daemon actually serves.

    When the primary is a hosted provider, ``llm.model`` holds *that* provider's id
    (e.g. ``meta-llama/Llama-3.3-70B-Instruct``), which Ollama would 404 on. Resolve
    against the daemon's installed tags instead, preferring the configured model,
    then the local default, then any installed non-embedding model.
    """
    installed = _installed_ollama_models(base_url)
    if not installed:
        # Daemon reachable but tag listing failed — trust the configured name only
        # if it looks like an Ollama tag rather than a hosted repo path.
        return configured if "/" not in configured else None

    def _match(name: str) -> str | None:
        return next((t for t in installed if t == name or t.split(":")[0] == name), None)

    for candidate in (configured, _OLLAMA_DEFAULT_MODEL):
        hit = _match(candidate)
        if hit:
            return hit
    # Last resort: first installed model that isn't an embedding-only tag.
    return next((t for t in installed if not any(e in t.lower() for e in _EMBED_HINTS)), None)


def _local_backups() -> list:
    """Backup factories for a hosted provider: local Ollama, then local GGUF SLM.

    Lets a hosted primary (HF Inference Providers, OpenAI, Anthropic, Cohere)
    degrade to a *generative* local model on a request-time failure — rate limit,
    billing lapse, network blip — instead of dropping straight to quotation-only
    extractive output. Probed lazily: an unreachable daemon costs nothing until a
    failure actually occurs. Extractive remains the terminal link in ResilientLLM.
    """
    s = get_settings()
    backups: list = []

    if _vllm_reachable(s.llm.vllm_base_url):

        def _vllm() -> LLM:
            from auralynq.llm.providers import VLLMLLM

            return VLLMLLM(s.llm.vllm_base_url, s.llm.vllm_model, s.llm.vllm_api_key)

        backups.append(_vllm)

    if _ollama_reachable(s.llm.base_url):
        model = _ollama_backup_model(s.llm.model, s.llm.base_url)
        if model is not None:

            def _ollama() -> LLM:
                from auralynq.llm.providers import OllamaLLM

                return OllamaLLM(model, s.llm.base_url)

            backups.append(_ollama)

    if _slm_available():

        def _slm() -> LLM:
            slm = _build_slm()
            if slm is None:
                raise RuntimeError("slm unavailable")
            return slm

        backups.append(_slm)

    return backups


def _build_slm() -> LLM | None:
    """Construct a SLMLlm, downloading the GGUF if not cached. Returns None on failure."""
    from auralynq.llm.slm import resolve_model_path, resolve_n_gpu_layers

    s = get_settings()
    path = resolve_model_path(s.llm.slm_repo, s.llm.slm_filename, s.huggingface_token)
    if path is None:
        return None
    n_layers = resolve_n_gpu_layers(s.llm.slm_n_gpu_layers)
    try:
        from auralynq.llm.providers import SLMLlm
        from auralynq.llm.resilient import ResilientLLM

        return ResilientLLM(SLMLlm(path, n_gpu_layers=n_layers, n_ctx=s.llm.slm_n_ctx))
    except Exception as exc:
        _log.warning("llm.slm_init_failed", error=str(exc))
        return None


def _resolve_auto() -> str:
    """The `auto` priority ladder, local-first and zero-cost.

    Single source of truth for both `build_llm()` and `resolved_provider()` — these
    were duplicated, so adding a backend to one silently desynced /health from what
    actually served. AirLLM is deliberately absent: minutes per answer is never a
    sane automatic choice, so it must be selected explicitly.
    """
    s = get_settings()

    if _vllm_reachable(s.llm.vllm_base_url):
        # A running vLLM server is a deliberate act by the operator — prefer it.
        return "vllm"
    if _ollama_reachable(s.llm.base_url):
        # Local Ollama: zero-cost, no data egress, works offline.
        return "ollama"
    if _slm_available():
        # Local GGUF SLM: GPU when CUDA present, CPU otherwise.
        return "slm"

    # Air-gap mode: external commercial providers are forbidden regardless of
    # which keys are present in the environment.
    if s.air_gapped:
        _log.info("llm.air_gapped", skipped=["anthropic", "openai", "cohere"])
        return "extractive"

    if s.anthropic_api_key and importlib.util.find_spec("anthropic"):
        return "anthropic"
    if s.openai_api_key and importlib.util.find_spec("openai"):
        return "openai"
    if s.cohere_api_key and importlib.util.find_spec("cohere"):
        return "cohere"
    return "extractive"


def build_llm(provider: str | None = None) -> LLM:
    s = get_settings()
    provider = provider or s.llm.provider

    if provider == "auto":
        provider = _resolve_auto()

    # Hard-fail: if air-gapped and a commercial provider was explicitly configured,
    # refuse rather than silently sending data out.
    if s.air_gapped and provider in ("openai", "anthropic", "cohere", "huggingface"):
        _log.warning(
            "llm.air_gapped_block",
            provider=provider,
            action="falling back to extractive",
        )
        return ExtractiveLLM()

    # Networked/commercial providers are wrapped so a request-time failure (bad
    # key, inactive billing, rate limit, network blip) degrades to extractive
    # instead of 500-ing the query (ADR-0003).
    try:
        if provider == "ollama":
            from auralynq.llm.providers import OllamaLLM
            from auralynq.llm.resilient import ResilientLLM

            return ResilientLLM(OllamaLLM(s.llm.model, s.llm.base_url))

        if provider == "vllm":
            from auralynq.llm.providers import VLLMLLM
            from auralynq.llm.resilient import ResilientLLM

            # An unreachable vLLM server degrades to the other local backends
            # rather than to quotation-only output.
            return ResilientLLM(
                VLLMLLM(s.llm.vllm_base_url, s.llm.vllm_model, s.llm.vllm_api_key),
                backups=_local_backups(),
            )

        if provider == "airllm":
            from auralynq.llm.providers import AirLLMLLM
            from auralynq.llm.resilient import ResilientLLM

            if not s.llm.airllm_enabled:
                _log.warning("llm.airllm_disabled", fallback="auto")
                return build_llm("auto")
            return ResilientLLM(
                AirLLMLLM(
                    s.llm.airllm_model,
                    compression=s.llm.airllm_compression,
                    max_new_tokens=s.llm.airllm_max_new_tokens,
                ),
                backups=_local_backups(),
            )

        if provider == "slm":
            slm = _build_slm()
            if slm is not None:
                return slm
            _log.warning("llm.slm_unavailable", fallback="extractive")
            return ExtractiveLLM()

        if provider == "openai":
            from auralynq.llm.providers import OpenAILLM
            from auralynq.llm.resilient import ResilientLLM

            return ResilientLLM(
                OpenAILLM(s.openai_api_key, _model_for("openai", s.llm.model)),
                backups=_local_backups(),
            )

        if provider == "anthropic":
            from auralynq.llm.providers import AnthropicLLM
            from auralynq.llm.resilient import ResilientLLM

            return ResilientLLM(
                AnthropicLLM(s.anthropic_api_key, _model_for("anthropic", s.llm.model)),
                backups=_local_backups(),
            )

        if provider == "cohere":
            from auralynq.llm.providers import CohereLLM
            from auralynq.llm.resilient import ResilientLLM

            return ResilientLLM(
                CohereLLM(s.cohere_api_key, _model_for("cohere", s.llm.model)),
                backups=_local_backups(),
            )

        if provider == "huggingface":
            # Powerful hosted models via HF Inference Providers (OpenAI-compatible
            # router). Explicit-only: never auto-selected, so a token present for
            # gated *downloads* never silently routes generation to a paid API.
            from auralynq.llm.providers import HuggingFaceLLM
            from auralynq.llm.resilient import ResilientLLM

            if not s.huggingface_token:
                # No token: prefer a local generative model over quotation-only.
                for make_backup in _local_backups():
                    try:
                        local = make_backup()
                    except Exception:
                        continue
                    _log.warning("llm.huggingface_no_token", fallback=local.name)
                    return ResilientLLM(local)
                _log.warning("llm.huggingface_no_token", fallback="extractive")
                return ExtractiveLLM()
            return ResilientLLM(
                HuggingFaceLLM(s.huggingface_token, _model_for("huggingface", s.llm.model)),
                backups=_local_backups(),
            )

    except Exception as exc:  # construction failure (e.g. missing sdk) → extractive
        _log.warning("llm.fallback_extractive", error=str(exc))

    _log.info("llm.using", provider="extractive")
    return ExtractiveLLM()


def resolved_provider() -> str:
    s = get_settings()
    if s.llm.provider != "auto":
        if s.air_gapped and s.llm.provider in ("openai", "anthropic", "cohere", "huggingface"):
            return "extractive"
        return s.llm.provider
    return _resolve_auto()


@functools.lru_cache(maxsize=1)
def get_llm() -> LLM:
    return build_llm()
