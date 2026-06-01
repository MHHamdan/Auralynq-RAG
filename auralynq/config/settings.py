"""Typed, env-driven configuration for Auralynq.

All settings are loaded from environment variables / `.env` via pydantic-settings.
Nested groups use the ``AURALYNQ_<GROUP>__<FIELD>`` convention (double underscore).
Only ``HUGGINGFACE_TOKEN`` is ever required, and only for gated HF assets.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["auto"]


class EmbeddingSettings(BaseSettings):
    provider: Literal["auto", "bge", "hash", "openai"] = "auto"
    model: str = "BAAI/bge-m3"
    dim: int = 1024
    device: Literal["auto", "cpu", "cuda"] = "auto"
    batch_size: int = 16


class VectorSettings(BaseSettings):
    backend: Literal["auto", "qdrant", "memory"] = "auto"
    url: str = "http://localhost:6333"
    collection: str = "auralynq"
    quantization: Literal["none", "scalar", "binary"] = "none"
    hnsw_m: int = 16


class RerankSettings(BaseSettings):
    provider: Literal["auto", "bge", "cohere", "none"] = "auto"
    model: str = "BAAI/bge-reranker-v2-m3"


class RetrievalSettings(BaseSettings):
    top_k: int = 20
    final_k: int = 6
    rrf_k: int = 60
    mmr_lambda: float = 0.6
    dense_weight: float = 0.6
    sparse_weight: float = 0.4


class LLMSettings(BaseSettings):
    provider: Literal["auto", "ollama", "openai", "anthropic", "cohere", "extractive"] = "auto"
    model: str = "llama3.2:3b"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.1
    max_tokens: int = 1024


class AgentSettings(BaseSettings):
    max_iters: int = 3
    latency_budget_ms: int = 15_000
    semantic_cache: bool = True
    cache_threshold: float = 0.93


class VoiceSettings(BaseSettings):
    asr_provider: Literal["auto", "faster_whisper", "whisperx", "null"] = "auto"
    asr_model: str = "base"
    tts_provider: Literal["auto", "kokoro", "null"] = "auto"
    tts_voice: str = "af_heart"
    diarize: bool = True
    vad: bool = True
    sample_rate: int = 16_000


class ServeSettings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    rate_limit_per_min: int = 120
    max_upload_mb: int = 50
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    # Optional bearer-token auth. Empty == open (local/demo). When set, all
    # endpoints except /health and /metrics require `Authorization: Bearer <key>`.
    api_key: str = ""


class TelemetrySettings(BaseSettings):
    enabled: bool = True
    phoenix_endpoint: str = "http://localhost:6006"
    otlp_endpoint: str = ""
    service_name: str = "auralynq"
    # Langfuse (optional hosted trace/eval). Activated when both LANGFUSE_* keys
    # are set; host defaults to Langfuse Cloud, override for self-hosted.
    langfuse_host: str = "https://cloud.langfuse.com"


class Settings(BaseSettings):
    """Root settings object. Instantiate via :func:`get_settings`."""

    model_config = SettingsConfigDict(
        env_prefix="AURALYNQ_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: Literal["local", "dev", "prod"] = "local"
    log_level: str = "INFO"
    log_json: bool = False
    data_dir: Path = Path("./data")
    reports_dir: Path = Path("./reports")
    seed: int = 42

    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    vector: VectorSettings = Field(default_factory=VectorSettings)
    rerank: RerankSettings = Field(default_factory=RerankSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    serve: ServeSettings = Field(default_factory=ServeSettings)
    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)

    # Well-known secrets (not prefixed). Empty string == "not configured".
    huggingface_token: str = Field(default="", alias="HUGGINGFACE_TOKEN")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    cohere_api_key: str = Field(default="", alias="COHERE_API_KEY")
    langfuse_public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "index"

    @property
    def storage_dir(self) -> Path:
        return self.data_dir / "storage"

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.reports_dir, self.index_dir, self.storage_dir):
            p.mkdir(parents=True, exist_ok=True)


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance (read once per process).

    Set ``AURALYNQ_DOTENV_DISABLED=1`` to skip reading a host ``.env`` entirely —
    used by the test suite so a populated server ``.env`` can't leak secrets/auth
    into deterministic offline tests.
    """
    if os.getenv("AURALYNQ_DOTENV_DISABLED") == "1":
        return Settings(_env_file=None)  # type: ignore[call-arg]
    return Settings()


def reload_settings() -> Settings:
    """Clear the cache and re-read settings (useful in tests)."""
    get_settings.cache_clear()
    return get_settings()
