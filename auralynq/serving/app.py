"""Auralynq FastAPI backend.

Async API with SSE token streaming for chat, a WebSocket voice channel, ingest /
query / voice / health / metrics / eval endpoints, request IDs, rate limiting and
safe file handling. All heavy work degrades to offline fallbacks (ADR-0003).
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections import Counter
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse

from auralynq import __version__
from auralynq.config import get_settings
from auralynq.providers import health_snapshot
from auralynq.serving.auth import AuthMiddleware
from auralynq.serving.errors import (
    AuralynqError,
    auralynq_error_handler,
    unhandled_error_handler,
)
from auralynq.serving.ratelimit import RateLimitMiddleware
from auralynq.serving.schemas import (
    CorpusClearConfirmRequest,
    CorpusClearPreviewResponse,
    CorpusDeleteDocumentConfirmRequest,
    CorpusDeleteDocumentPreviewResponse,
    CorpusDeleteReportResponse,
    CorpusSummaryResponse,
    HealthResponse,
    IngestResponse,
    ObservabilitySummaryResponse,
    QueryRequest,
    QueryResponse,
    StatusResponse,
    SuggestionsResponse,
    VoiceResponse,
)
from auralynq.telemetry import configure_logging, get_logger, init_telemetry

_log = get_logger("auralynq.api")
_METRICS: Counter = Counter()
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")

# --- Backend intent classifier -------------------------------------------
# Classifies questions that must skip RAG and be answered from system state.
# Intercepts at the query endpoint level before answer_question() is called.

_CORPUS_MGMT_PATTERNS = [
    re.compile(
        r"\b(delete|remove|wipe|clear|purge|erase|drop|reset)\b"
        r".*\b(document|file|corpus|collection|index|vector|upload|pdf|docx"
        r"|data|db|library|everything|all|last|uploaded)\b",
        re.I,
    ),
    re.compile(
        r"\b(delete|remove|wipe|clear|purge|erase|drop|reset)\b.*\b(my|the)\b",
        re.I,
    ),
    re.compile(
        r"\b(how|can i|how do i|can you|please)\b"
        r".*\b(delete|remove|clear|wipe|reset|purge)\b",
        re.I,
    ),
    re.compile(
        r"\b(delete|remove)\b.*\b(last|latest|most recent|previously)\b"
        r".*\b(document|file|upload|doc|pdf)\b",
        re.I,
    ),
    re.compile(
        r"\b(clear|wipe|reset)\b.*\b(corpus|collection|vectors?|index|everything)\b",
        re.I,
    ),
    re.compile(r"\b(remove|delete)\b.*permanently", re.I),
]

_CORPUS_INVENTORY_PATTERNS = [
    re.compile(
        r"\b(how many|how much|count|number of)\b"
        r".*\b(document|file|doc|vector|entit|page|chunk|upload|index)\b",
        re.I,
    ),
    re.compile(r"\bhow many\b", re.I),  # "how many documents do I have?"
    re.compile(
        r"\b(what|which|list|show)\b.*\b(document|file|doc|upload|index)\b",
        re.I,
    ),
    re.compile(
        r"\b(do i have|are there|is there)\b"
        r".*\b(document|file|doc|upload|index|arabic|english|french)\b",
        re.I,
    ),
    re.compile(r"\bare there any (documents?|files?|docs?)\b", re.I),
    re.compile(r"\b(list|show)\b.*\b(document|file|doc|indexed)\b", re.I),
    re.compile(r"\bin my (corpus|collection|library|index)\b", re.I),
    re.compile(r"\bwhat (documents?|files?) (do i|have i|are)\b", re.I),
    re.compile(
        r"\b(last|latest|most recent|recently)\b.*\b(document|file|upload|index|add)\b",
        re.I,
    ),
    re.compile(r"\b(what was|what is) the last\b", re.I),
    re.compile(r"\bhow many.*so far\b", re.I),
    re.compile(r"\b(my|the) (corpus|collection) (is|has|contains|include)\b", re.I),
]

_APP_HELP_PATTERNS = [
    re.compile(
        r"\bhow (do|can|to) (i|you|we)\b.*(upload|ingest|index|add|use|start|begin|reindex)\b",
        re.I,
    ),
    re.compile(
        r"\bhow (does|to) (upload|ingest|index|reindex|delete|remove)\b",
        re.I,
    ),
    re.compile(
        r"\b(what|which) (file types?|formats?|documents?)\b.*(support|accept|upload|ingest)\b",
        re.I,
    ),
]


def _classify_corpus_intent(question: str) -> str | None:
    """Return a corpus-management intent label, or None for normal RAG questions."""
    q = question.strip()
    for pat in _CORPUS_MGMT_PATTERNS:
        if pat.search(q):
            return "corpus_management"
    for pat in _CORPUS_INVENTORY_PATTERNS:
        if pat.search(q):
            return "corpus_inventory"
    for pat in _APP_HELP_PATTERNS:
        if pat.search(q):
            return "app_help"
    return None


def _system_answer_for_intent(intent: str, question: str) -> dict[str, Any]:
    """Build a system-sourced answer dict for non-RAG intents."""
    from auralynq.serving.corpus import corpus_summary, suggested_questions

    summary = corpus_summary(use_cache=False)
    doc_count = summary.get("indexed_document_count", 0)
    vector_count = summary.get("vector_count", 0)
    entity_count = summary.get("entity_count", 0)
    titles = summary.get("document_titles", [])
    last_doc = summary.get("last_document_title")

    if intent == "corpus_inventory":
        lines = [
            f"Your corpus currently contains **{doc_count} document(s)**,"
            f" **{vector_count} vector(s)**, and **{entity_count} entities**."
        ]
        if titles:
            doc_list = "\n".join(f"  - {t}" for t in titles[:20])
            lines.append(f"\n**Indexed documents:**\n{doc_list}")
        if last_doc:
            lines.append(f"\n**Last document added:** {last_doc}")
        langs = summary.get("languages", [])
        if langs:
            lines.append(f"\n**Languages detected:** {', '.join(langs)}")
        if not titles:
            lines = ["Your corpus is **empty**. Upload a document to begin."]
        answer = "\n".join(lines)

    elif intent == "corpus_management":
        answer = (
            "To manage your corpus, use the **Ingest** panel → **Manage Corpus** section.\n\n"
            "Available actions:\n"
            "- **Delete last document**: removes the most recently indexed file\n"
            "- **Clear all corpus**: removes all documents, vectors, and entities\n"
            "- **Delete a specific document**: select from the document list\n\n"
            f"Current corpus: **{doc_count}** document(s), **{vector_count}** vectors."
        )

    else:  # app_help
        answer = (
            "**Getting started with Auralynq:**\n\n"
            "1. **Upload documents**: drag a file onto the Ingest panel\n"
            "2. **Ask questions**: type or speak a question in the composer\n"
            "3. **Manage corpus**: use Ingest → Manage Corpus to delete or clear\n"
            "4. **Supported formats**: PDF, DOCX, HTML, Markdown, TXT, WAV, MP3, M4A"
        )

    rationale = f"retrieval skipped: system/{intent} intent detected"
    trace_step = {
        "id": 1,
        "name": "intent_classifier",
        "label": f"System: {intent}",
        "status": "success",
        "duration_ms": 0,
        "warnings": [],
        "attributes": {"intent": intent},
    }
    return {
        "answer": answer,
        "status": "answered",
        "citations": [],
        "route": intent,
        "route_confidence": 1.0,
        "route_rationale": rationale,
        "path_evidence": [],
        "seeds": [],
        "iterations": 0,
        "confidence": 1.0,
        "evidence_coverage": 0.0,
        "cached": False,
        "elapsed_ms": 0.0,
        "trace": [
            {
                "name": "intent_classifier",
                "duration_ms": 0,
                "attributes": {"intent": intent},
                "events": [],
            }
        ],
        "trace_steps": [trace_step],
        "detected_entities": [],
        "suggested_questions": suggested_questions(3, summary),
        "warnings": [],
    }


async def _aiter_sync(gen: Iterator[Any]) -> AsyncIterator[Any]:
    """Adapt a blocking sync generator to an async iterator by advancing it one
    item per ``asyncio.to_thread`` call, so the event loop stays free to service
    other requests between yielded tokens."""
    sentinel = object()

    def _next() -> Any:
        try:
            return next(gen)
        except StopIteration:
            return sentinel

    while True:
        item = await asyncio.to_thread(_next)
        if item is sentinel:
            return
        yield item


def create_app() -> FastAPI:
    s = get_settings()
    configure_logging(level=s.log_level, json=s.log_json)
    s.ensure_dirs()
    if s.telemetry.enabled:
        init_telemetry(s.telemetry.service_name, s.telemetry.otlp_endpoint)

    app = FastAPI(
        title="Auralynq API",
        version=__version__,
        description="Talk to Your Data — agentic voice RAG with PathRAG.",
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=s.serve.cors_origins, allow_methods=["*"], allow_headers=["*"]
    )
    app.add_middleware(RateLimitMiddleware, limit_per_min=s.serve.rate_limit_per_min)
    app.add_middleware(AuthMiddleware, api_key=s.serve.api_key)
    app.add_exception_handler(AuralynqError, auralynq_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)

    @app.middleware("http")
    async def request_id_mw(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        request.state.request_id = rid
        _METRICS["requests_total"] += 1
        t0 = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        _METRICS["request_ms_total"] += int((time.perf_counter() - t0) * 1000)
        return response

    # ------------------------------------------------------------- health --
    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        snap = health_snapshot()
        try:
            from auralynq.vectorstore.factory import get_store

            snap["index"] = {"vectors": get_store().count()}
        except Exception:  # pragma: no cover
            snap["index"] = {"vectors": 0}
        return HealthResponse(**snap)

    @app.get("/version")
    async def version() -> JSONResponse:
        # Stable service identity for orchestration / compatibility checks.
        import platform

        return JSONResponse(
            {
                "name": "auralynq",
                "version": __version__,
                "api": "v1",
                "python": platform.python_version(),
                "env": get_settings().env,
            }
        )

    @app.get("/ready")
    async def ready() -> JSONResponse:
        # Readiness (vs /health liveness): is the index queryable yet? Returns 503
        # until at least one vector is indexed, so orchestrators don't route
        # traffic to an empty instance.
        try:
            from auralynq.vectorstore.factory import get_store

            n = get_store().count()
        except Exception:  # pragma: no cover
            n = 0
        ready = n > 0
        return JSONResponse(
            {"ready": ready, "vectors": n},
            status_code=200 if ready else 503,
        )

    @app.get("/metrics")
    async def metrics() -> JSONResponse:
        return JSONResponse(dict(_METRICS))

    # -------------------------------------------------- status / corpus ----
    @app.get("/status", response_model=StatusResponse)
    async def status() -> StatusResponse:
        from auralynq.serving.corpus import corpus_summary

        snap = health_snapshot()
        s = get_settings()
        try:
            from auralynq.vectorstore.factory import get_store

            vectors = get_store().count()
        except Exception:  # pragma: no cover
            vectors = 0
        from auralynq.telemetry.langfuse_export import langfuse_enabled

        return StatusResponse(
            status=snap["status"],
            version=snap["version"],
            env=snap["env"],
            providers=snap["providers"],
            index={"vectors": vectors},
            corpus=corpus_summary(),
            tracing={
                "provider": "langfuse+phoenix" if langfuse_enabled() else "in-process",
                "phoenix_endpoint": s.telemetry.phoenix_endpoint,
                "langfuse_host": s.telemetry.langfuse_host,
                "enabled": s.telemetry.enabled,
            },
        )

    @app.get("/corpus/summary", response_model=CorpusSummaryResponse)
    async def corpus_summary_ep() -> CorpusSummaryResponse:
        from auralynq.serving.corpus import corpus_summary

        return CorpusSummaryResponse(**corpus_summary())

    # -------------------------------------------------- corpus management ---
    @app.get("/corpus/inventory", response_model=CorpusSummaryResponse)
    async def corpus_inventory_ep() -> CorpusSummaryResponse:
        from auralynq.serving.corpus import corpus_summary

        return CorpusSummaryResponse(**corpus_summary(use_cache=False))

    @app.post("/corpus/clear/preview", response_model=CorpusClearPreviewResponse)
    async def corpus_clear_preview_ep() -> CorpusClearPreviewResponse:
        from auralynq.serving.corpus_manager import corpus_clear_preview

        return CorpusClearPreviewResponse(**corpus_clear_preview())

    @app.post("/corpus/clear/confirm", response_model=CorpusDeleteReportResponse)
    async def corpus_clear_confirm_ep(req: CorpusClearConfirmRequest) -> CorpusDeleteReportResponse:
        from auralynq.serving.corpus_manager import corpus_clear_confirm

        try:
            report = await asyncio.to_thread(corpus_clear_confirm, req.phrase)
        except ValueError as e:
            raise AuralynqError("wrong_phrase", detail=str(e), status_code=400) from e
        return CorpusDeleteReportResponse(**report)

    @app.get("/corpus/documents/last/preview", response_model=CorpusDeleteDocumentPreviewResponse)
    async def corpus_delete_last_preview_ep() -> CorpusDeleteDocumentPreviewResponse:
        from auralynq.serving.corpus_manager import corpus_delete_last_preview

        return CorpusDeleteDocumentPreviewResponse(**corpus_delete_last_preview())

    @app.post("/corpus/documents/last/confirm", response_model=CorpusDeleteReportResponse)
    async def corpus_delete_last_confirm_ep(
        req: CorpusDeleteDocumentConfirmRequest,
    ) -> CorpusDeleteReportResponse:
        from auralynq.serving.corpus_manager import corpus_delete_last_confirm

        try:
            report = await asyncio.to_thread(corpus_delete_last_confirm, req.phrase)
        except ValueError as e:
            raise AuralynqError("wrong_phrase", detail=str(e), status_code=400) from e
        return CorpusDeleteReportResponse(**report)

    @app.get(
        "/corpus/documents/{doc_id}/preview",
        response_model=CorpusDeleteDocumentPreviewResponse,
    )
    async def corpus_delete_doc_preview_ep(doc_id: str) -> CorpusDeleteDocumentPreviewResponse:
        if not re.match(r"^[0-9a-f]{8,64}$", doc_id):
            raise AuralynqError("invalid_doc_id", status_code=400)
        from auralynq.serving.corpus_manager import corpus_delete_document_preview

        return CorpusDeleteDocumentPreviewResponse(**corpus_delete_document_preview(doc_id))

    @app.post("/corpus/documents/{doc_id}/confirm", response_model=CorpusDeleteReportResponse)
    async def corpus_delete_doc_confirm_ep(
        doc_id: str, req: CorpusDeleteDocumentConfirmRequest
    ) -> CorpusDeleteReportResponse:
        if not re.match(r"^[0-9a-f]{8,64}$", doc_id):
            raise AuralynqError("invalid_doc_id", status_code=400)
        from auralynq.serving.corpus_manager import corpus_delete_document_confirm

        try:
            report = await asyncio.to_thread(corpus_delete_document_confirm, doc_id, req.phrase)
        except ValueError as e:
            raise AuralynqError("wrong_phrase", detail=str(e), status_code=400) from e
        return CorpusDeleteReportResponse(**report)

    @app.get("/suggestions", response_model=SuggestionsResponse)
    async def suggestions_ep(limit: int = 4) -> SuggestionsResponse:
        from auralynq.serving.corpus import corpus_summary, suggested_questions

        summary = corpus_summary()
        return SuggestionsResponse(
            suggestions=suggested_questions(max(1, min(limit, 8)), summary),
            corpus_indexed=bool(summary.get("indexed")),
        )

    @app.get("/observability/summary", response_model=ObservabilitySummaryResponse)
    async def observability_summary() -> ObservabilitySummaryResponse:
        from auralynq.telemetry.langfuse_export import langfuse_enabled

        s = get_settings()
        reqs = _METRICS.get("requests_total", 0)
        total_ms = _METRICS.get("request_ms_total", 0)
        return ObservabilitySummaryResponse(
            requests_total=reqs,
            query_total=_METRICS.get("query_total", 0) + _METRICS.get("query_stream_total", 0),
            avg_request_ms=round(total_ms / reqs, 2) if reqs else 0.0,
            tracing_provider="langfuse+phoenix" if langfuse_enabled() else "in-process",
            phoenix_url=s.telemetry.phoenix_endpoint or None,
            langfuse_host=s.telemetry.langfuse_host or None,
        )

    # ------------------------------------------------------------- query ---
    @app.post("/query", response_model=QueryResponse)
    async def query(req: QueryRequest, request: Request) -> QueryResponse:
        _METRICS["query_total"] += 1
        intent = _classify_corpus_intent(req.question)
        if intent:
            data = await asyncio.to_thread(_system_answer_for_intent, intent, req.question)
            return QueryResponse(request_id=request.state.request_id, **data)

        from auralynq.agent.runner import answer_question

        # answer_question is CPU/network-bound and synchronous; run it off the event
        # loop so concurrent requests aren't blocked behind it.
        res = await asyncio.to_thread(
            answer_question,
            req.question,
            final_k=req.final_k,
            use_cache=req.use_cache,
            route_hint=req.route_hint or "",
        )
        return QueryResponse(request_id=request.state.request_id, **res.to_dict())

    @app.post("/query/stream")
    async def query_stream(req: QueryRequest, request: Request) -> EventSourceResponse:
        _METRICS["query_stream_total"] += 1
        intent = _classify_corpus_intent(req.question)

        async def event_gen():
            if intent:
                # System answer — emit as a single final event, no tokens
                data = await asyncio.to_thread(_system_answer_for_intent, intent, req.question)
                yield {"event": "meta", "data": json.dumps({
                    "type": "meta",
                    "route": intent,
                    "confidence": 1.0,
                    "rationale": f"retrieval skipped: {intent}",
                    "seeds": [],
                    "path_evidence": [],
                })}
                yield {"event": "final", "data": json.dumps({"type": "final", **data})}
                return

            from auralynq.agent.runner import stream_answer_question

            # Drive the blocking token generator one step at a time in a worker
            # thread (_aiter_sync) so streaming never stalls the event loop.
            gen = stream_answer_question(req.question, final_k=req.final_k)
            async for event in _aiter_sync(gen):
                if await request.is_disconnected():
                    close = getattr(gen, "close", None)
                    if close is not None:
                        close()  # stop the underlying generator promptly
                    break
                yield {"event": event["type"], "data": json.dumps(event)}

        return EventSourceResponse(event_gen())

    # ------------------------------------------------------------ ingest ---
    @app.post("/ingest", response_model=IngestResponse)
    async def ingest(request: Request, file: UploadFile = File(...)) -> IngestResponse:
        s = get_settings()
        safe = _SAFE_NAME.sub("_", Path(file.filename or "upload.bin").name)
        inbox = s.storage_dir / "uploads"
        inbox.mkdir(parents=True, exist_ok=True)
        dest = inbox / safe
        size = 0
        limit = s.serve.max_upload_mb * 1024 * 1024
        with dest.open("wb") as fh:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > limit:
                    dest.unlink(missing_ok=True)
                    raise AuralynqError(
                        "file_too_large", detail=f"max {s.serve.max_upload_mb} MB", status_code=413
                    )
                fh.write(chunk)
        from auralynq.pipeline import build_index
        from auralynq.serving.corpus import invalidate_corpus_cache

        try:
            stats = build_index(inbox, rebuild=False)
        finally:
            # Remove the raw upload after indexing; only embeddings are retained.
            dest.unlink(missing_ok=True)
        invalidate_corpus_cache()  # refresh corpus stats/suggestions immediately
        _METRICS["ingest_total"] += 1
        return IngestResponse(
            documents=stats["documents"],
            chunks=stats["chunks_indexed"],
            skipped=stats["skipped"],
            request_id=request.state.request_id,
        )

    # ------------------------------------------------------------- voice ---
    @app.post("/voice", response_model=VoiceResponse)
    async def voice(request: Request, file: UploadFile = File(...)) -> VoiceResponse:
        s = get_settings()
        safe = _SAFE_NAME.sub("_", Path(file.filename or "audio.wav").name)
        tmp = s.storage_dir / "voice_in"
        tmp.mkdir(parents=True, exist_ok=True)
        dest = tmp / safe
        # Stream with the same per-upload size cap as /ingest so a large audio
        # file cannot exhaust memory or disk before we even start ASR.
        size = 0
        limit = s.serve.max_upload_mb * 1024 * 1024
        try:
            with dest.open("wb") as fh:
                while chunk := await file.read(1 << 20):
                    size += len(chunk)
                    if size > limit:
                        dest.unlink(missing_ok=True)
                        raise AuralynqError(
                            "file_too_large",
                            detail=f"max {s.serve.max_upload_mb} MB",
                            status_code=413,
                        )
                    fh.write(chunk)
            from auralynq.voice.loop import run_voice_turn

            res = run_voice_turn(audio_path=dest, speak=True)
        finally:
            # Securely unlink the transient audio buffer regardless of outcome.
            dest.unlink(missing_ok=True)
        _METRICS["voice_total"] += 1
        audio_url = "/voice/audio" if res.audio_out_path else None
        return VoiceResponse(
            transcript=res.transcript,
            answer=res.answer,
            citations=res.citations,
            route=res.route,
            audio_out_url=audio_url,
            asr_provider=res.asr_provider,
            tts_provider=res.tts_provider,
            request_id=request.state.request_id,
        )

    @app.get("/voice/audio")
    async def voice_audio() -> FileResponse:
        out = get_settings().storage_dir / "tts_out.wav"
        if not out.exists():
            raise AuralynqError("no_audio", status_code=404)
        return FileResponse(str(out), media_type="audio/wav")

    @app.websocket("/ws/voice")
    async def ws_voice(ws: WebSocket) -> None:
        await ws.accept()
        s = get_settings()
        tmp = s.storage_dir / "ws_voice"
        tmp.mkdir(parents=True, exist_ok=True)
        buffer = bytearray()
        ws_limit = s.serve.max_upload_mb * 1024 * 1024
        try:
            while True:
                msg = await ws.receive()
                if msg.get("bytes") is not None:
                    if len(buffer) + len(msg["bytes"]) > ws_limit:
                        await ws.send_json(
                            {"type": "error", "detail": f"buffer exceeds {s.serve.max_upload_mb} MB"}
                        )
                        buffer.clear()
                        continue
                    buffer += msg["bytes"]
                    await ws.send_json({"type": "ack", "bytes": len(buffer)})
                elif msg.get("text") is not None:
                    ctrl = json.loads(msg["text"])
                    if ctrl.get("action") == "end":
                        dest = tmp / f"{uuid.uuid4().hex[:8]}.wav"
                        try:
                            dest.write_bytes(bytes(buffer) or _silence())
                            from auralynq.voice.loop import run_voice_turn

                            res = run_voice_turn(audio_path=dest, speak=False)
                        finally:
                            dest.unlink(missing_ok=True)
                        await ws.send_json({"type": "transcript", "text": res.transcript})
                        await ws.send_json(
                            {
                                "type": "final",
                                "answer": res.answer,
                                "citations": res.citations,
                                "route": res.route,
                            }
                        )
                        buffer.clear()
                    elif ctrl.get("action") == "reset":
                        buffer.clear()
        except (WebSocketDisconnect, RuntimeError):  # client closed
            return

    # -------------------------------------------------------------- eval ---
    @app.get("/eval/report")
    async def eval_report() -> JSONResponse:
        path = get_settings().reports_dir / "eval_report.json"
        if not path.exists():
            return JSONResponse(
                {"status": "pending", "detail": "run `make eval` to generate a report"}
            )
        return JSONResponse(json.loads(path.read_text(encoding="utf-8")))

    @app.get("/bench/report")
    async def bench_report() -> JSONResponse:
        path = get_settings().reports_dir / "bench_report.json"
        if not path.exists():
            return JSONResponse({"status": "pending", "detail": "run `make bench`"})
        return JSONResponse(json.loads(path.read_text(encoding="utf-8")))

    return app


def _silence(seconds: float = 0.5, sr: int = 16_000) -> bytes:
    import wave
    from io import BytesIO

    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(b"\x00\x00" * int(sr * seconds))
    return buf.getvalue()


app = create_app()
