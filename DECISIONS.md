# Architecture Decision Records — Auralynq

Short ADRs. Each: **Context → Decision → Rationale → Alternatives rejected.**

---

## ADR-0001 — Product & package naming

**Context.** The product must use one consistent name across package, CLI, services, UI, and docs.

**Decision.** Product = **Auralynq**. Python package / modules / folders / CLI / services = `auralynq`. MCP server = `auralynq-mcp`. Container prefix = `auralynq-*`. Tagline = "Talk to Your Data". **PathRAG** is preserved only as the name of the graph-retrieval algorithm/paper.

**Rationale.** Single source of truth prevents drift; a repo-wide name audit (`make name-audit`) enforces it.

**Alternatives rejected.** Mixed/generic naming (e.g. a "Voice-RAG"-style label, or branding the product after the PathRAG algorithm) — causes branding drift and import confusion.

---

## ADR-0002 — Python 3.11 baseline (spec asked 3.12)

**Context.** Spec requests Python 3.12; the build/CI environment ships Python 3.11.14.

**Decision.** Target `requires-python = ">=3.11"`. Code is written to be 3.11/3.12 compatible; CI matrices both.

**Rationale.** Use the interpreter actually present so `make setup`/tests run at $0 with no extra downloads. No 3.12-only syntax is used.

**Alternatives rejected.** Forcing a 3.12 toolchain install — slower setup, no functional benefit for this codebase.

---

## ADR-0003 — Lightweight core + optional heavy extras + deterministic fallbacks

**Context.** The spec mandates "runs locally at $0", "missing paid keys never break the demo", yet also wants bge-m3, Qdrant, whisper, pyannote, Kokoro, langgraph, ragas, etc. — multi-GB GPU stacks.

**Decision.** Core deps are pure-Python/light (pydantic, fastapi, numpy, networkx, httpx). Every heavy/paid integration lives in a `pyproject` extra and is **imported lazily**. Each subsystem ships a deterministic, dependency-free **fallback**:
- Embeddings → hashing-bag embedder (stable, seeded) when bge-m3 absent.
- Vector store → in-process `MemoryStore` when `qdrant-client`/server absent.
- LLM → extractive synthesizer (citation-faithful) when Ollama/keys absent.
- ASR/TTS → null/sine + transcript-passthrough providers when models absent.
- Agent → native Python state machine mirroring the LangGraph graph when `langgraph` absent.
- Eval → numpy metric implementations when `ragas`/`jiwer` absent.

**Rationale.** The whole platform — ingest → index → retrieve → agent → serve → eval → MCP → UI — is exercisable and unit-tested offline. Upgrading to real models is a config flag, not a code change. This is the single most important design choice for reproducibility.

**Alternatives rejected.** Hard-requiring the ML stack — breaks `$0` guarantee, makes CI heavy/flaky, slows onboarding.

---

## ADR-0004 — Provider abstraction via factories + `auto` resolution

**Context.** Many swappable backends (embeddings, LLM, rerank, ASR, TTS, vector).

**Decision.** Each subsystem exposes a `Protocol`/ABC and a `factory.py` that resolves `provider=auto` by probing env keys and importable packages, falling back deterministically. Selection is logged once at startup.

**Rationale.** One config surface; testable resolution logic; honest "what's actually running" reporting at `/health`.

**Alternatives rejected.** Hard-wired imports; conditional logic scattered across call-sites.

---

## ADR-0005 — Podman-first containerization

**Context.** Target machine has no Docker; Podman 3.4 with `podman-compose` (the `podman compose` subcommand is absent).

**Decision.** `scripts/check_container_runtime.sh` detects `podman compose` then `podman-compose`; all Makefile stack targets call it. Compose file is `compose.yml`. Images are rootless-friendly (no privileged ports, named volumes).

**Rationale.** Matches the actual environment; degrades gracefully with a clear message if neither is present.

**Alternatives rejected.** Docker / docker-compose — not installed, explicitly disallowed.

---

## ADR-0006 — PathRAG isolated, attributed, flow-pruned

**Context.** Graph retrieval must implement PathRAG (Chen et al., 2025) with flow-based pruning.

**Decision.** PathRAG lives only under `auralynq/retrieval/pathrag/`. We implement node retrieval → relational path expansion (bounded hops) → resource-flow-based path pruning → path-reliability scoring → deterministic path-to-text prompting with golden-region (most-reliable-at-edges) ordering. The algorithm is a clean-room implementation from the paper; attribution + license notes in `THIRD_PARTY.md`.

**Rationale.** Clear module boundary, testable scoring, no licensing entanglement.

**Alternatives rejected.** Vendoring a third-party repo wholesale (license/maintenance risk).

---

## ADR-0007 — Relational knowledge graph in NetworkX + SQLite-style JSON persistence

**Context.** Need entities, relations, provenance, spans, timestamps, reliability — small/local.

**Decision.** Build the KG with `networkx.MultiDiGraph`; persist as versioned JSON (`graph.json`) plus a node/edge provenance table. Reliability scores are computed from corroboration count + source trust.

**Rationale.** Zero-infra, diff-able, fast for laptop-scale corpora; trivially swappable for a real graph DB later.

**Alternatives rejected.** Neo4j (infra weight), pure in-memory (no persistence).

---

## ADR-0008 — Agent as explicit typed state machine

**Context.** Spec lists 11 nodes with latency budgets and iteration caps.

**Decision.** A single Pydantic `AgentState` flows through nodes. When `langgraph` is installed we compile a real `StateGraph`; otherwise an equivalent ordered executor runs the same node functions. Every node emits a trace span with timing; the trajectory is returned in the API response and rendered in the UI.

**Rationale.** Identical behavior with/without langgraph; full observability; deterministic tests.

**Alternatives rejected.** langgraph as a hard dependency (heavy, breaks $0 default).

---

## ADR-0009 — SSE for chat tokens, WebSocket for voice

**Context.** Need token streaming and a bidirectional voice channel.

**Decision.** Chat uses Server-Sent Events (`sse-starlette`) — simple, proxy-friendly, unidirectional. Voice uses a WebSocket carrying control + audio frames for the push-to-talk loop.

**Rationale.** Right tool per channel; SSE avoids WS overhead for plain token streams.

**Alternatives rejected.** WS for everything (more complex client), polling (latency).

---

## ADR-0010 — Eval harness owns all benchmark numbers

**Context.** README must not contain invented numbers.

**Decision.** Every metric in the README is produced by `make eval` / `make bench` and written under `reports/`. Unmeasured metrics are explicitly marked "pending". A frozen golden set + drift check guards regressions.

**Rationale.** Honesty + reproducibility; the README is generated from real artifacts.

**Alternatives rejected.** Hand-written marketing numbers.

---

## ADR-0011 — Optional bearer-token API auth (open-by-default)

**Context.** The serving layer needs a production auth story, but the headline
promise is a zero-friction local `$0` demo. These pull in opposite directions.

**Decision.** Auth is gated by `AURALYNQ_SERVE__API_KEY`. Empty (default) ⇒ the API
is open — the local demo and tests are unaffected. When set, an `AuthMiddleware`
requires `Authorization: Bearer <key>` on all endpoints except `/health` and
`/metrics` (and CORS pre-flight), returning a structured 401. Tokens are compared
with `hmac.compare_digest` (constant-time).

**Rationale.** One env var flips a local demo into an authenticated deployment with
no code change; health/metrics stay public for orchestrators/probes; constant-time
compare avoids timing leaks.

**Alternatives rejected.** Always-on auth (breaks the $0 demo), per-route decorators
(scattered, easy to miss an endpoint), full OAuth/JWT (over-engineered for a
single-tenant local-first tool; can layer on later behind the same middleware).
