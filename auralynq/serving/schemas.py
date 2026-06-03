"""Pydantic request/response schemas for the FastAPI backend."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    final_k: int | None = Field(default=None, ge=1, le=50)
    use_cache: bool | None = None


class Citation(BaseModel):
    marker: int
    source: str
    locator: str = ""
    source_type: str = "unknown"
    speaker: str | None = None
    start_s: float | None = None
    end_s: float | None = None
    page: int | None = None


class QueryResponse(BaseModel):
    answer: str
    status: str = "answered"
    citations: list[dict[str, Any]] = Field(default_factory=list)
    route: str = "fast"
    route_confidence: float = 0.0
    route_rationale: str = ""
    path_evidence: list[dict[str, Any]] = Field(default_factory=list)
    seeds: list[str] = Field(default_factory=list)
    iterations: int = 0
    confidence: float = 0.0
    evidence_coverage: float = 0.0
    cached: bool = False
    elapsed_ms: float = 0.0
    trace: list[dict[str, Any]] = Field(default_factory=list)
    trace_steps: list[dict[str, Any]] = Field(default_factory=list)
    detected_entities: list[str] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list)
    insufficient_evidence_reason: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    provider_status: list[dict[str, str]] = Field(default_factory=list)
    request_id: str = ""


class CorpusSummaryResponse(BaseModel):
    indexed: bool = False
    indexed_document_count: int = 0
    vector_count: int = 0
    document_titles: list[str] = Field(default_factory=list)
    source_types: dict[str, int] = Field(default_factory=dict)
    top_entities: list[dict[str, Any]] = Field(default_factory=list)
    entity_count: int = 0
    last_indexed: str | None = None


class SuggestionsResponse(BaseModel):
    suggestions: list[str] = Field(default_factory=list)
    corpus_indexed: bool = False


class StatusResponse(BaseModel):
    status: str = "ok"
    version: str = ""
    env: str = ""
    providers: list[dict[str, str]] = Field(default_factory=list)
    index: dict[str, Any] = Field(default_factory=dict)
    corpus: dict[str, Any] = Field(default_factory=dict)
    tracing: dict[str, Any] = Field(default_factory=dict)


class ObservabilitySummaryResponse(BaseModel):
    requests_total: int = 0
    query_total: int = 0
    avg_request_ms: float = 0.0
    tracing_provider: str = "in-process"
    phoenix_url: str | None = None
    langfuse_host: str | None = None


class IngestResponse(BaseModel):
    documents: int
    chunks: int
    skipped: int
    request_id: str = ""


class VoiceResponse(BaseModel):
    transcript: str
    answer: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    route: str = "fast"
    audio_out_url: str | None = None
    asr_provider: str = "null"
    tts_provider: str | None = None
    request_id: str = ""


class HealthResponse(BaseModel):
    status: str
    version: str
    env: str
    providers: list[dict[str, str]]
    hf_token_present: bool
    index: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: str
    detail: str = ""
    request_id: str = ""
