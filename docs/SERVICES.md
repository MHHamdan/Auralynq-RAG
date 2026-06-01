# Auralynq — Service Topology

Auralynq is built as a set of composable services from **one codebase and image
set**. Each service is a thin entrypoint over the shared `auralynq` package, so
they deploy and scale independently while sharing one tested core (ADR-0018).

```
                         ┌─────────── public ───────────┐
   browser ──HTTPS──▶ caddy / ingress ──▶ web (UI + /api proxy) ──▶ api
   MCP client ──HTTPS──▶ (ingress /mcp) ─────────────────────────▶ mcp
                                                                    │
                                          ┌─────────────────────────┼─────────────┐
                                          ▼                         ▼             ▼
                                       qdrant (vectors)        phoenix (traces)  (LLM/embed
                                          ▲                                       providers:
   files ──▶ worker ──(index)────────────┘                                       cohere/openai/…)
```

## Services

| Service | Role | Image | Port | Public? | State | Scaling |
|---------|------|-------|------|---------|-------|---------|
| **web** | Next.js UI + same-origin `/api` proxy (injects bearer token) | `auralynq-web` | 3000 | via ingress | stateless | horizontal (HPA) |
| **api** | FastAPI — SSE chat, WS voice, ingest/query/health/ready/version/metrics | `auralynq-api` | 8000 | internal | stateless* | horizontal (HPA) |
| **mcp** | MCP server (7 tools) over streamable-HTTP, bearer-authed | `auralynq-api` | 8765 | optional ingress | stateless* | horizontal (HPA) |
| **worker** | Background ingestion (inbox → index) | `auralynq-api` | — | no | queue/inbox | independent (1×, or shared-volume/queue) |
| **qdrant** | Hybrid vector store | `qdrant/qdrant` | 6333/4 | internal | **stateful** (PVC) | vertical / cluster |
| **phoenix** | Trace UI + OTLP collector | `arizephoenix/phoenix` | 6006/4317 | internal | ephemeral | 1× |
| **caddy** | TLS reverse proxy (compose only; k8s uses ingress) | `auralynq-caddy` | 8443 | **yes** | stateless | 1× |

\* *Stateless against Qdrant: the index lives in Qdrant, so api/mcp pods hold no
durable state and scale freely. With the in-memory vector backend they are NOT
stateless — use `AURALYNQ_VECTOR__BACKEND=qdrant` in multi-replica deployments.*

## Why one image for api/mcp/worker

They are the same Python package invoked with different entrypoints
(`uvicorn …app`, `python -m …mcp_server.server`, `python -m …serving.worker`).
One image = one build, one test surface, one provenance — they diverge only by
`args` and which env they read. This is the "start small, keep updating as
microservices" path: split by **process/role**, not by duplicated code.

## Deployment modes

- **Local / single host** — `make stack-up` (Podman Compose). Caddy fronts TLS;
  services reach each other by container name via the dnsname-patched CNI
  (ADR-0014). See the README *Remote / server deployment* section.
- **Cluster / production** — `kubectl apply -k deploy/k8s` (Kubernetes). Each
  service is its own Deployment+Service; api/mcp/web autoscale via HPA against a
  single Qdrant StatefulSet; the web UI is the only public surface (Ingress+TLS).
  See `deploy/k8s/`.

## Scaling guidance

- **api / mcp / web** → scale horizontally (HPA on CPU; raise `maxReplicas`).
  They are stateless against Qdrant.
- **qdrant** → scale vertically (CPU/RAM) or move to a Qdrant cluster; it is the
  one stateful tier. Back it with a fast PVC.
- **worker** → one replica by default (its inbox is per-pod). For parallel
  ingestion, back the inbox with a shared `ReadWriteMany` PVC or a real queue
  (roadmap), then scale out.
- **provider load** → LLM/embedding/rerank calls go to external providers
  (Cohere/OpenAI/…); a broken/throttled provider degrades to offline fallbacks
  (ADR-0003) rather than cascading failures.

## Configuration & secrets

All services read the same `AURALYNQ_*` env (see `.env.example`). In k8s, non-secret
config is a ConfigMap and secrets a Secret (`deploy/k8s/config.yaml`); only
`HUGGINGFACE_TOKEN` is ever required, and only for gated assets. Missing optional
keys degrade to local fallbacks, so every service starts and stays healthy at $0.
