# Auralynq API / worker image. Multi-stage, rootless-friendly.
FROM docker.io/library/python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps for audio + parsing (kept minimal). ffmpeg powers audio decode.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 curl procps \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for layer caching. faster-whisper + soundfile give
# real ASR for the voice endpoint without pulling torch (unlike the full [voice]
# extra's silero-vad); faster-whisper uses CTranslate2 and its own bundled VAD.
COPY pyproject.toml README.md ./
COPY auralynq ./auralynq
RUN pip install -e ".[ingest,eval,vector]" "faster-whisper>=1.0" "soundfile>=0.12"

COPY scripts ./scripts

# Non-root user (rootless containers map this safely). Create the data/reports
# mountpoints owned by the runtime user *before* declaring volumes so Podman
# initializes named volumes with the correct (writable) ownership.
RUN useradd -m -u 10001 auralynq \
    && mkdir -p /app/data /app/reports \
    && chown -R auralynq:auralynq /app
USER auralynq
VOLUME ["/app/data"]

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "auralynq.serving.app:app", "--host", "0.0.0.0", "--port", "8000"]
