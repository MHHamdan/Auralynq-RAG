"""Background model-pull jobs with live progress.

A pull can run for many minutes. Tying it to the HTTP request that started it
means closing the modal (or any proxy read timeout) kills progress reporting, so
the download runs as a detached asyncio task and the UI subscribes to a job.

Job state survives the subscriber: reconnecting re-reads the snapshot and
resumes streaming from wherever the download has got to.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

from auralynq.modelfit.ollama_client import (
    OllamaUnreachable,
    classify_pull_error,
    ollama_base_url,
    stream_pull,
)
from auralynq.telemetry import get_logger

_log = get_logger("auralynq.modelfit.pull")

PullPhase = Literal["queued", "manifest", "downloading", "verifying", "success", "error"]

# Progress frames are coalesced to this interval so a fast local pull cannot
# flood the SSE channel with thousands of near-identical updates.
_EMIT_INTERVAL_S = 0.25

# Completed jobs are kept this long so a late reconnect still sees the outcome.
_JOB_TTL_S = 3600.0


@dataclass
class PullJob:
    job_id: str
    model_id: str
    tag: str
    phase: PullPhase = "queued"
    status_text: str = "Queued"
    completed_bytes: int = 0
    total_bytes: int = 0
    percent: float = 0.0
    speed_bps: float = 0.0
    eta_s: float | None = None
    message: str = ""
    error: str = ""
    error_status: int = 0
    layers_done: int = 0
    layers_total: int = 0
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    # Per-blob byte counters, so progress is aggregate across layers rather than
    # snapping back to 0% every time Ollama starts a new blob.
    _layers: dict[str, tuple[int, int]] = field(default_factory=dict, repr=False)
    _subscribers: list[asyncio.Queue[dict[str, Any]]] = field(default_factory=list, repr=False)
    _task: asyncio.Task[None] | None = field(default=None, repr=False)

    @property
    def terminal(self) -> bool:
        return self.phase in ("success", "error")

    def snapshot(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "model_id": self.model_id,
            "tag": self.tag,
            "phase": self.phase,
            "status_text": self.status_text,
            "completed_bytes": self.completed_bytes,
            "total_bytes": self.total_bytes,
            "percent": round(self.percent, 1),
            "speed_bps": round(self.speed_bps),
            "eta_s": round(self.eta_s) if self.eta_s is not None else None,
            "layers_done": self.layers_done,
            "layers_total": self.layers_total,
            "message": self.message,
            "error": self.error,
            "error_status": self.error_status or None,
            "elapsed_s": round((self.finished_at or time.time()) - self.started_at, 1),
        }


_jobs: dict[str, PullJob] = {}


def get_job(job_id: str) -> PullJob | None:
    return _jobs.get(job_id)


def list_jobs() -> list[dict[str, Any]]:
    return [j.snapshot() for j in _jobs.values()]


def find_active_job(model_id: str) -> PullJob | None:
    """An in-flight pull for this model, so a re-click re-attaches instead of duplicating."""
    for job in _jobs.values():
        if job.model_id == model_id and not job.terminal:
            return job
    return None


def _reap() -> None:
    now = time.time()
    stale = [
        jid
        for jid, j in _jobs.items()
        if j.terminal and j.finished_at and now - j.finished_at > _JOB_TTL_S
    ]
    for jid in stale:
        _jobs.pop(jid, None)


def _publish(job: PullJob) -> None:
    snap = job.snapshot()
    for q in list(job._subscribers):
        with contextlib.suppress(asyncio.QueueFull):
            q.put_nowait(snap)


def start_pull(model_id: str, tag: str) -> PullJob:
    """Start (or re-attach to) a background pull for `tag`."""
    _reap()
    existing = find_active_job(model_id)
    if existing:
        return existing

    job = PullJob(job_id=uuid.uuid4().hex[:12], model_id=model_id, tag=tag)
    _jobs[job.job_id] = job
    job._task = asyncio.create_task(_run_pull(job))
    _log.info("modelfit.pull.start", job_id=job.job_id, tag=tag, base_url=ollama_base_url())
    return job


async def _run_pull(job: PullJob) -> None:
    last_emit = 0.0
    window_t0 = time.time()
    window_bytes0 = 0

    def finish_error(raw: str) -> None:
        status, human = classify_pull_error(job.tag, raw)
        job.phase = "error"
        job.error = human
        job.error_status = status
        job.status_text = "Failed"
        job.finished_at = time.time()
        _log.warning("modelfit.pull.error", job_id=job.job_id, tag=job.tag, status=status, raw=raw)

    try:
        async for frame in stream_pull(job.tag):
            if frame.get("error"):
                finish_error(str(frame["error"]))
                break

            status_text = str(frame.get("status") or "")
            job.status_text = status_text or job.status_text

            total = int(frame.get("total") or 0)
            completed = int(frame.get("completed") or 0)
            digest = str(frame.get("digest") or "")
            if total > 0 and digest:
                job._layers[digest] = (completed, total)
                job.completed_bytes = sum(c for c, _ in job._layers.values())
                job.total_bytes = sum(t for _, t in job._layers.values())
                job.layers_total = len(job._layers)
                job.layers_done = sum(1 for c, t in job._layers.values() if c >= t)
                job.percent = min(100.0, job.completed_bytes / job.total_bytes * 100.0)
                job.phase = "downloading"
            # Order matters: Ollama's trailing steps include "writing manifest",
            # which is a post-download step, not the initial manifest fetch.
            elif any(k in status_text.lower() for k in ("verif", "writ", "digest")):
                job.phase = "verifying"
            elif "manifest" in status_text.lower():
                job.phase = "manifest"

            if status_text.lower() == "success":
                job.phase = "success"
                job.percent = 100.0
                job.message = f"Pulled {job.tag} successfully."
                job.finished_at = time.time()
                break

            now = time.time()
            dt = now - window_t0
            if dt >= 1.0:
                job.speed_bps = max(0.0, (job.completed_bytes - window_bytes0) / dt)
                window_t0, window_bytes0 = now, job.completed_bytes
                if job.speed_bps > 0 and job.total_bytes > job.completed_bytes:
                    job.eta_s = (job.total_bytes - job.completed_bytes) / job.speed_bps

            if now - last_emit >= _EMIT_INTERVAL_S:
                last_emit = now
                _publish(job)
        else:
            # Stream ended without an explicit success frame — older Ollama builds
            # close the connection once the blobs are written.
            if not job.terminal:
                job.phase = "success"
                job.percent = 100.0
                job.message = f"Pulled {job.tag} successfully."
                job.finished_at = time.time()

    except OllamaUnreachable as exc:
        job.phase = "error"
        job.error = str(exc)
        job.error_status = 503
        job.status_text = "Ollama unreachable"
        job.finished_at = time.time()
    except asyncio.CancelledError:
        job.phase = "error"
        job.error = "Pull cancelled."
        job.error_status = 499
        job.finished_at = time.time()
        _publish(job)
        raise
    except Exception as exc:  # pragma: no cover - defensive
        finish_error(str(exc))

    _publish(job)
    _log.info("modelfit.pull.done", job_id=job.job_id, tag=job.tag, phase=job.phase)


async def subscribe(job: PullJob) -> AsyncIterator[dict[str, Any]]:
    """Yield state snapshots until the job reaches a terminal phase."""
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
    job._subscribers.append(queue)
    try:
        yield job.snapshot()  # immediate state, so a reconnect renders instantly
        while not job.terminal:
            try:
                snap = await asyncio.wait_for(queue.get(), timeout=15.0)
            except TimeoutError:
                # Keepalive: a silent minute on a big layer must not look like a hang.
                yield job.snapshot()
                continue
            yield snap
            if snap.get("phase") in ("success", "error"):
                return
        yield job.snapshot()
    finally:
        with contextlib.suppress(ValueError):
            job._subscribers.remove(queue)
