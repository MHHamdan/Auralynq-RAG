# Running Auralynq

Two ways to run: **containers (Podman)** for a full production-shaped stack, or
**local CLI/dev** at $0. Below covers both, plus deploying to a **different
machine**. Podman only — no Docker, no sudo required.

---

## TL;DR (this server)

The stack is normally already running. Otherwise:

```bash
cd /home/mhamdan/Auralynq
make stack-up      # start;  make stack-down to stop
```

Open **https://172.24.50.21:8443** (accept the one-time self-signed cert warning).

---

## 1. Run on a DIFFERENT machine

The whole stack is three published images on GHCR (public) plus a small `.env`.
You do **not** need the source to run it — only `compose.yml`, the `Caddyfile`,
and an `.env`.

### Prerequisites on the new machine
- **Podman** + a Podman Compose (`podman compose` *or* `podman-compose`).
- Ports: open inbound **TCP `<HTTPS_PORT>`** (default 8443) in the firewall. No
  other port needs to be public.
- No GHCR login needed — the images are public.

### Step 1 — get the deploy files
Clone the repo (or copy just `compose.yml`, `containers/Caddyfile`,
`scripts/`, `Makefile`):

```bash
git clone https://github.com/MHHamdan/Auralynq.git && cd Auralynq
```

### Step 2 — create `.env` (git-ignored; never commit it)
Replace `<SERVER>` with the new machine's IP **or** domain, and set your keys
(all optional — missing keys degrade to offline fallbacks):

```bash
cat > .env <<'EOF'
# --- where browsers reach it ---
AURALYNQ_HTTPS_PORT=8443
AURALYNQ_CERT_HOST=<SERVER>                       # IP or domain (cert SAN)
AURALYNQ_SITE_ADDRESS=:8443                       # or https://your.domain (Let's Encrypt)
AURALYNQ_SERVE__CORS_ORIGINS=["https://<SERVER>:8443"]
NEXT_PUBLIC_API_BASE=/api                         # browser → same-origin proxy
AURALYNQ_BIND_INTERNAL=127.0.0.1                  # internal services off the public NIC

# --- run the PUBLISHED images from GHCR (no local build needed) ---
AURALYNQ_IMAGE_PREFIX=ghcr.io/mhhamdan/auralynq-
AURALYNQ_IMAGE_TAG=0.1.0

# --- providers (all optional; degrade to local fallbacks) ---
AURALYNQ_LLM__PROVIDER=cohere                     # or: auto | ollama | extractive
COHERE_API_KEY=...                                # your key(s)
# OPENAI_API_KEY= / ANTHROPIC_API_KEY= / HUGGINGFACE_TOKEN=

# --- API auth (recommended when public). Empty = open ---
AURALYNQ_SERVE__API_KEY=<openssl rand -hex 24>
EOF
```

### Step 3 — start
```bash
make stack-up
```
Browse to **https://<SERVER>:8443**.

### Step 4 — add data
- **UI**: the Ingest panel → upload a PDF/DOCX/TXT/audio.
- **CLI**:
  ```bash
  podman cp mydoc.pdf auralynq-api:/app/data/corpus/
  podman exec auralynq-api auralynq index --input /app/data/corpus
  ```

### The one gotcha: TLS cert on a new host
The Caddy image bakes a **self-signed cert** whose SAN is `AURALYNQ_CERT_HOST`.
The GHCR `auralynq-caddy` image was built with `localhost`, so on a new IP the
browser shows a cert warning (functionally fine — click *Advanced → Proceed*).
For a clean cert, pick one:

- **Self-signed for your IP** — rebuild just caddy locally (needs the repo):
  ```bash
  AURALYNQ_CERT_HOST=<SERVER> podman build -t auralynq-caddy:0.1.0 \
    -f containers/caddy.Dockerfile .
  # then drop AURALYNQ_IMAGE_PREFIX for caddy, or retag/push your own
  ```
- **Trusted (real domain)** — set `AURALYNQ_SITE_ADDRESS=https://your.domain`
  and `AURALYNQ_TLS=internal`; Caddy auto-provisions Let's Encrypt (needs the
  domain's DNS → this host and ports 80/443 reachable).

### Rootless networking note
On hosts where rootless Podman's CNI lacks container DNS, `make stack-up`
auto-patches the network conflist (CNI 0.4.0 + dnsname) — no sudo. If you use a
working Docker/Podman 4 + netavark host, service-name DNS works out of the box and
this is a no-op.

---

## 2. Full production stack on THIS machine (from source)

```bash
cd /home/mhamdan/Auralynq
make images          # build api/web/caddy locally (versioned + OCI labels)
make stack-up        # start; make stack-down to stop; make stack-logs to tail
```

`make stack-up` starts: **caddy** (public TLS) + web + api + mcp + worker + qdrant
+ phoenix. Only the HTTPS port is public; everything else binds loopback.

After changing code, rebuild then **fully cycle** (podman-compose pins image IDs):
```bash
make images
podman-compose -f compose.yml down && make stack-up
```

---

## 3. Local CLI / dev ($0, no containers)

```bash
make setup                 # uv venv + light deps
make data && make index    # sample corpus → index
make demo                  # end-to-end: typed + voice, prints cited answers
auralynq ask "How does PathRAG prune relational paths?"
auralynq serve             # FastAPI on :8000
auralynq-mcp               # MCP server over stdio (Claude Desktop, IDEs)
```

---

## URLs & ports

| Service | URL | Public? |
|---------|-----|---------|
| **Web UI** | `https://<SERVER>:8443` | ✅ (only this) |
| API docs | `https://<SERVER>:8443/api/docs` | via proxy |
| Phoenix traces | `http://127.0.0.1:6006` | loopback (SSH-tunnel to view) |
| Qdrant / API / MCP | loopback only | ❌ internal |

## Health checks

```bash
podman ps
curl -sk https://<SERVER>:8443/api/health
curl -sk -X POST https://<SERVER>:8443/api/query \
  -H 'Content-Type: application/json' -d '{"question":"hi"}'
```

## Troubleshooting

- **Cert warning** — expected with self-signed; *Advanced → Proceed*, or use a domain.
- **502 right after `make stack-up`** — web is still booting; retry in a few seconds.
- **No answer in chat after a code change** — rebuild the web image and **fully
  cycle** (`down` then `make stack-up`); hard-refresh the browser (Ctrl/Cmd-Shift-R).
- **Can't reach from another machine** — open inbound TCP 8443 in the firewall.
- **Secrets** live only in `.env` (git-ignored). Never commit it.
