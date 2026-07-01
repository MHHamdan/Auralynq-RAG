# Deploying Auralynq to a Hugging Face Space

> **Status: planned, not yet implemented.** The `deploy/huggingface/` artifacts
> (Dockerfile, entrypoint, env template, Space README template) referenced
> below are being built as a follow-up to this guide. Nothing here has been
> published to Hugging Face automatically, and no Space deployment should be
> assumed to work until `deploy/huggingface/` exists in the repo and has been
> smoke-tested. This document describes the intended design so contributors
> can track progress and review the plan before it lands.

## Why a Space needs its own packaging

Auralynq's default topology (see [podman.md](podman.md)) is 7 containers
behind a Caddy TLS proxy — that doesn't map onto a single HF Space container.
A Space needs one image that either serves the API and a static/SSR frontend
together, or runs both processes under a small supervisor inside one
container.

## Planned modes

**Mode A — Lightweight demo Space**
- No secrets required to run.
- Ships with the [demo corpus](../../examples/demo_corpus/) pre-indexed or
  indexed on first boot.
- Forces the offline/extractive fallback path (hash embeddings, in-memory
  vector store, extractive answering) — no model downloads, no GPU.
- Uploads disabled by default (`AURALYNQ_ALLOW_UPLOADS=false`) so a public,
  unauthenticated Space can't accumulate arbitrary user documents.
- Demonstrates: chat, citations, trace panel, visual grounding, ModelFit
  hardware page (CPU-only numbers).

**Mode B — Full Docker Space**
- Reads provider keys from HF Space **Secrets** (never Variables, never
  baked into the image).
- Optionally attaches persistent `/data` if the Space has persistent storage
  enabled; otherwise storage is ephemeral and reset on every Space restart —
  this will be stated plainly in the Space README so nobody mistakes it for
  durable storage.
- Uploads may be enabled (`AURALYNQ_ALLOW_UPLOADS=true`) only when the
  operator understands the privacy implications of a public Space
  persisting user-uploaded documents.

## Planned environment variables

```bash
AURALYNQ_HF_SPACE=true
AURALYNQ_DEMO_MODE=true
AURALYNQ_PUBLIC_DEMO=true
AURALYNQ_ALLOW_UPLOADS=false            # true only if you understand the persistence/privacy trade-off
AURALYNQ_DATA_DIR=/data/auralynq
AURALYNQ_SERVE__API_KEY=                # set via Space Secrets if the Space needs auth
NEXT_PUBLIC_API_BASE=/api
AURALYNQ_LLM__PROVIDER=auto
AURALYNQ_VECTOR__BACKEND=memory
AURALYNQ_EMBEDDING__PROVIDER=hash
AURALYNQ_VISUAL__ENABLED=true
AURALYNQ_MODELFIT__ENABLED=true
```

None of these exist in the codebase yet (verified — grepped for
`AURALYNQ_HF_SPACE` / `AURALYNQ_DEMO_MODE` across `auralynq/`, `web/`, and all
`.env`/`config` examples: no hits as of this writing). They're specified here
so the implementation and this doc land in the same change.

## Variables vs. Secrets (Hugging Face concept, applies once the Space exists)

- **Variables**: visible to anyone who can view the Space's settings/logs if
  misconfigured — fine for `AURALYNQ_DEMO_MODE`, `NEXT_PUBLIC_API_BASE`, etc.
  Never put a provider key in a Variable.
- **Secrets**: encrypted, not visible in the Space UI or logs — use for
  `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `COHERE_API_KEY`,
  `AURALYNQ_SERVE__API_KEY`, `HUGGINGFACE_TOKEN`.

## Persistent vs. ephemeral storage

- Free/CPU Spaces without persistent storage attached: everything under
  `AURALYNQ_DATA_DIR` is wiped on every Space restart/redeploy. Uploaded
  documents, the vector index, and the page cache do not survive.
- Spaces with **Persistent Storage** enabled: `/data` survives restarts. Mode
  B is designed to use this when available and to say so explicitly in the
  Space README so users don't assume privacy guarantees that don't hold for
  a public Space regardless of storage durability.

## Hardware

- Default target: **CPU basic** — the whole point of the lightweight mode is
  that it needs no GPU.
- Upgrading to GPU: only meaningful if you also enable a real embedding/LLM
  provider; document the specific hardware tier once ModelFit numbers exist
  for it (no fabricated numbers — see `docs/benchmarks.md` once it exists).

## Duplicating the Space

Once published, "Duplicate this Space" carries over Variables but not
Secrets — anyone duplicating a Mode B Space must re-enter their own provider
keys; they never inherit the original operator's keys.

## Next steps

- No containers at all → [no-podman.md](no-podman.md)
- Full Podman stack → [podman.md](podman.md)
- Remote server deployment → [server.md](server.md)
