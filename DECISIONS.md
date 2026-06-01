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

---

## ADR-0012 — Deployment hardening for remote/server exposure

**Context.** The stack is run on a remote server reachable by browsers on other
machines, with all ports bound to `0.0.0.0`. The earlier setup ran api/worker as
container-root, exposed Qdrant + Phoenix publicly with no auth, had no restart
policies/healthchecks, and (for rootless DNS reasons) reached Qdrant via the host
gateway. Enabling API auth naively would either break the browser UI or leak the
key into the client bundle.

**Decision.**
- **Network surface:** only the **web UI** and **API** publish on `0.0.0.0`.
  **Qdrant and Phoenix** bind to `${AURALYNQ_BIND_INTERNAL:-127.0.0.1}` — on this
  host the podman bridge gateway (`10.88.0.1`/cni-podman0), reachable by containers
  (via `host.containers.internal`) and host tooling, but **not** from the external
  NIC. Default `127.0.0.1` keeps a clean host secure out of the box.
- **API auth:** `AURALYNQ_SERVE__API_KEY` (empty == open). The browser never holds
  the key: the **web container runs a same-origin `/api/*` proxy** (Next.js route
  handler) that injects `Authorization: Bearer` server-side and streams responses.
  So `NEXT_PUBLIC_API_BASE=/api` — no IP and no secret are baked into the bundle.
- **Least privilege:** api/worker drop the `user: "0:0"` override and run as the
  image's non-root `auralynq` (uid 10001); all services get
  `security_opt: ["no-new-privileges"]`, `restart: unless-stopped`, and
  healthchecks. Named volumes (`auralynq-data`, `auralynq-reports`) initialize with
  the image's non-root owner so writes succeed without host-ownership clashes.

**Rationale.** Satisfies "expose only UI+API", "enable API auth", and "never expose
secrets" simultaneously; the proxy also removes CORS as an attack surface (browser
calls are same-origin). Restart + healthchecks give crash recovery. TLS / public
reverse proxy is intentionally deferred to a separate step.

**Alternatives rejected.** Baking the key into the browser bundle (leaks the secret);
breaking the UI when auth is on (fails the "UI reachable" goal); binding internal
services to `127.0.0.1` only (the rootless API can't reach host loopback — no working
inter-container DNS on this Podman 3.4/CNI host); fixing DNS (dnsname/aardvark not
available here).

---

## ADR-0013 — TLS reverse proxy (Caddy), single public HTTPS port

**Context.** The hardened stack (ADR-0012) exposed plaintext HTTP on the API/UI
ports. Production remote access needs TLS, ideally a single public entrypoint.

**Decision.** Add a **Caddy** reverse-proxy service as the ONLY container published
on `0.0.0.0` (default `:8443`). It terminates TLS and forwards to the web container
(`auralynq-web:3000`), which serves the UI and proxies `/api/*` to the API. web,
api, qdrant, phoenix only bind to `${AURALYNQ_BIND_INTERNAL:-127.0.0.1}` (loopback)
plus the shared container network. TLS uses a **self-signed cert baked into the
Caddy image** (`containers/caddy.Dockerfile`) with the server IP + localhost as
SANs, served via an explicit `tls /certs/site.crt /certs/site.key` directive —
reliable for an IP / no-domain host (Caddy's on-demand internal-CA issuance is
unreliable for bare-IP sites). HTTP/3 is disabled (rootless can't size the QUIC
UDP buffer). `flush_interval -1` keeps SSE streaming + WebSocket voice unbuffered.

**Rationale.** One public TLS port; the browser only ever talks to Caddy; the API
key never leaves the server (web `/api` proxy injects it). For a real domain, set
`AURALYNQ_SITE_ADDRESS=https://your.domain` + `AURALYNQ_TLS=internal` (or ACME).

**Alternatives rejected.** `tls internal` for a bare-IP site (handshake fails — no
leaf cert for IP SNI); HTTP/3 (broken UDP buffer on rootless); terminating TLS in
the app (re-implements a proxy, no cert automation).

---

## ADR-0014 — No-sudo fix for rootless container DNS (CNI 0.4.0 + dnsname)

**Context.** This host runs **rootless Podman 3.4 with CNI**. Two defects broke
inter-container networking: (1) podman generates network conflists with
`cniVersion: 1.0.0`, but the installed **`firewall` CNI plugin only supports
≤0.4.0**, so it fails validation and collapses the plugin chain; (2) the default
`podman` network ships **without the `dnsname` plugin**, so there is no container
DNS at all. Earlier ADR-0012 worked around this with brittle bridge-IP wiring and
shared network namespaces. A proper fix via podman 4 / netavark needs root — but
the whole point of rootless Podman is to avoid sudo.

**Decision.** Fix it **without sudo** by rewriting the user-owned CNI conflists in
`~/.config/cni/net.d/`: pin `cniVersion` to `0.4.0` (which `firewall`, `bridge` and
`dnsname` all support) and append the `dnsname` plugin if absent. `scripts/stack_up.sh`
does this idempotently before `up`. With DNS restored, all services share
podman-compose's default network and address peers by **container_name**
(`auralynq-qdrant` / `auralynq-api` / `auralynq-web`) — eliminating the bridge-IP
guessing and shared-netns hacks. `dnsname` requires the `dnsmasq` binary (present)
and the plugin binary at `/usr/lib/cni/dnsname` (present; the rootless plugin dir
is set in `~/.config/containers/containers.conf`).

**Rationale.** Pure user-space, persists across `down`/`up`, and restores the
clean service-name networking Podman is supposed to provide. Supersedes the
bridge-IP workaround noted in ADR-0012.

**Alternatives rejected.** podman 4 + netavark (needs root); `external` networks in
compose (podman-compose 1.5.0 ignores them — attaches to the default net anyway);
shared network namespace for every service (couples lifecycles, can't publish
per-container ports); service-name aliases (dnsname resolves container_name, not
the compose service name, on this version).

---

## ADR-0015 — MCP as a first-class microservice (stdio + streamable-HTTP)

**Context.** The MCP server exposes Auralynq's 7 tools but was stdio-only — usable
by a local client that spawns the process, not by remote clients. The product goal
is to "serve production-ready around the world" as composable microservices.

**Decision.** Keep the transport-agnostic tool functions
(`auralynq/mcp_server/tools.py`) as the single source of truth, and make the server
**transport-selectable** via `--transport` / `AURALYNQ_MCP_TRANSPORT`:
`stdio` (default, local), `streamable-http` (remote microservice on
`AURALYNQ_MCP_HOST:PORT`, default `:8765`), or `sse` (legacy). A dedicated
`auralynq-mcp` container in `compose.yml` runs the HTTP transport (internal-only;
front with the Caddy TLS proxy for public exposure). An integration test drives
the real stdio protocol end-to-end (client → server → tool) and auto-skips when
the optional SDK is absent.

**Rationale.** One tool implementation, many entry points (CLI, FastAPI, local
MCP, remote MCP). HTTP transport lets agents/IDEs anywhere call the same grounded
RAG + PathRAG + voice tools — the microservices foundation the roadmap needs —
without duplicating logic.

**Alternatives rejected.** A bespoke REST shim around the tools (re-implements MCP,
loses client compatibility); HTTP-only (breaks the zero-config local Claude Desktop
flow); embedding MCP in the FastAPI app (couples two servers with different
lifecycles and auth models).

---

## ADR-0016 — Bearer-token auth for the MCP HTTP transports

**Context.** ADR-0015 made MCP remotely callable over HTTP. An open HTTP MCP
endpoint exposes the full ingest/search/agent toolset to anyone who can reach it —
unacceptable for public deployment.

**Decision.** Add an ASGI `MCPAuthMiddleware` wrapped around FastMCP's
`streamable_http_app()` / `sse_app()` (served via uvicorn in `_serve_http`). It
requires `Authorization: Bearer <key>` when a key is configured, returning a
structured 401 otherwise; comparison is constant-time (`hmac.compare_digest`).
Key resolution: `AURALYNQ_MCP_API_KEY` (dedicated) wins, else
`AURALYNQ_SERVE__API_KEY` (reuse the HTTP API key). Empty ⇒ open. The **stdio
transport is never gated** (it is local — the client spawns the process), so the
zero-config Claude Desktop flow is unaffected.

**Rationale.** Mirrors the HTTP API's auth model (ADR-0011) for consistency; one
env var turns the remote MCP microservice from open to authenticated with no code
change; constant-time compare avoids timing leaks. Combined with the Caddy TLS
proxy (ADR-0013) the token travels encrypted.

**Alternatives rejected.** OAuth/JWT (over-engineered for a single-tenant tool;
can layer behind the same middleware later); gating stdio (breaks local clients);
relying only on network isolation (defense-in-depth — auth + internal binding +
TLS are complementary).
