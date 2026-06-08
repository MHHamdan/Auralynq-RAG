<div align="center">

# 🎙️ Auralynq

### *Talk to Your Data — Grounded, Cited, Visually Verified*

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js-15-black.svg)](https://nextjs.org)
[![Podman](https://img.shields.io/badge/runtime-Podman-892CA0.svg)](https://podman.io)

A **local-first, voice-native, agentic RAG platform** with hybrid vector retrieval,
PPR-augmented PathRAG graph reasoning, 13 pluggable RAG strategies, visual source
grounding with exact span-level bounding boxes, and a full-screen document inspection
workspace. Grounded answers with citations you can visually verify against the original
PDF. Runs at **$0** on a laptop; upgrades to GPU models via env flags.

[Quickstart](#-quickstart) · [Architecture](#-architecture) · [Auralynq-RAG](#-auralynq-rag-contribution) · [Visual Grounding](#-visual-source-grounding) · [Benchmarks](#-benchmarks) · [Decisions](DECISIONS.md)

</div>

---

## One-line pitch

**Auralynq** lets you talk — text or voice — to your own documents and get grounded,
cited answers you can *visually verify*: click any citation and a full-screen workspace
opens with the original PDF page, exact evidence regions highlighted, extracted text
blocks on the side, and claim-level support status. An adaptive agentic loop with
13 pluggable RAG strategies, always-visible trace rail, and calibrated confidence
scoring. Built for research — every design decision is documented and reversible.

---

## 🏗 Architecture

### System overview

```
╔══════════════════════════════════════════════════════════════════════════════════╗
║                           AURALYNQ — SYSTEM MAP                                ║
╠════════════════════╦═══════════════════════════════════╦════════════════════════╣
║      INGEST        ║        AURALYNQ-RAG ENGINE         ║   SOURCE WORKSPACE     ║
╠════════════════════╣                                    ╠════════════════════════╣
║                    ║  ┌── Strategy Registry (13) ────┐  ║  ┌── Citation Panel ─┐ ║
║  PDF  DOCX  HTML   ║  │  ● Auralynq-RAG  [default]  │  ║  │ [1] doc · p.2     │ ║
║  MD   TXT   WAV    ║  │  ● Hybrid Vector             │  ║  │ [2] doc · p.4     │ ║
║  MP3  M4A          ║  │  ● Keyword BM25              │  ║  │ [Supported] ...   │ ║
║         │          ║  │  ○ Self-RAG  (experimental)  │  ║  └───────────────────┘ ║
║  pdfplumber        ║  │  ○ CRAG      (experimental)  │  ║                        ║
║  layout blocks     ║  │  ○ Adaptive  (experimental)  │  ║  ┌── PDF Viewer ─────┐ ║
║  bbox per chunk    ║  │  · GraphRAG  (planned)       │  ║  │ ┌───────────────┐ │ ║
║         │          ║  │  · RAPTOR    (planned)       │  ║  │ │  PAGE IMAGE   │ │ ║
║  pdf2image         ║  │  · LightRAG  (planned×3)     │  ║  │ │ [1]▓▓▓▓▓▓▓▓▓ │ │ ║
║  page PNGs @144DPI ║  │  · Self-RAG+ (planned)       │  ║  │ │ [2]░░░░░░░░░ │ │ ║
║         │          ║  └──────────────────────────────┘  ║  │ └───────────────┘ │ ║
║  Chunks + spans    ║                                    ║  │ Zoom · fit · nav  │ ║
║  VG metadata       ║  ┌── Agentic Loop ──────────────┐  ║  └───────────────────┘ ║
║                    ║  │  Planner                     │  ║                        ║
║  Qdrant            ║  │  Adaptive Router             │  ║  ┌── Evidence Panel ─┐ ║
║  dense + sparse    ║  │  Hybrid Retriever            │  ║  │ paragraph · span  │ ║
║  hybrid vectors    ║  │  PathRAG + PPR               │  ║  │ "cited snippet…"  │ ║
║                    ║  │  Dual-Signal Critic          │  ║  │ rel 84% conf 91%  │ ║
║  Knowledge Graph   ║  │  Query Rewriter              │  ║  └───────────────────┘ ║
║  entities/rels     ║  │  Synthesizer                 │  ║                        ║
║  PathRAG traversal ║  │  Self-Check                  │  ║  Full-screen modal     ║
║                    ║  │  Citation Validator          │  ║  3-panel layout        ║
║  VG Resolver       ║  └──────────────────────────────┘  ║  Escape to close       ║
║  span→page→none    ║                                    ║  ← → page navigate     ║
╚════════════════════╩═══════════════════════════════════╩════════════════════════╝
         │                        │                               │
         ▼                        ▼                               ▼
   /ingest endpoint         /query/stream                  /api/documents/
   SSE streaming            SSE streaming                  {id}/pages/{n}/
   VG metadata              visual_grounding               image | layout
   stored in Qdrant         in final event                 endpoints
```

### Detailed pipeline flowchart

```mermaid
flowchart TD
    subgraph Ingest["📥 Ingest Pipeline"]
        direction TB
        A["PDF / DOCX / HTML / MD / TXT"] --> PL["pdfplumber\nlayout block extraction\nbbox per text block"]
        AU["WAV / MP3 / M4A"] --> ASR["ASR + diarization\n+ speaker timestamps"]
        PL --> CH["Chunks + SourceSpan\n+ VG metadata (page, bbox)"]
        ASR --> CH
        CH --> IMG["pdf2image @ 144 DPI\npage PNG cache"]
        CH --> EMB["Embeddings\nbge-m3 / hash fallback"]
        EMB --> VS[("Qdrant\ndense + sparse\nhybrid vectors")]
        CH --> KG[("Knowledge Graph\nentities / relations\nPageRank index")]
        IMG --> PC["Page cache\ndata/page_cache/{doc_id}/\npage_NNNN.png"]
        CH --> DM["doc_meta.json\npage_dimensions\nvg_version\nn_pages"]
    end

    subgraph Strategies["⚡ RAG Strategy Registry (13)"]
        direction LR
        S1["● Auralynq-RAG\ndefault · fast"]
        S2["● Hybrid Vector\nfast"]
        S3["● Keyword BM25\nfast"]
        S4["○ Self-RAG\nexperimental"]
        S5["○ CRAG\nexperimental"]
        S6["○ Adaptive\nexperimental"]
        SP["· GraphRAG · RAPTOR\n· LightRAG × 3\n· Self-RAG+ · HippoRAG\nplanned / requires setup"]
    end

    subgraph Agent["🤖 Auralynq Agentic Loop"]
        direction TB
        Q["Query\ntext / voice"] --> PLA["Planner\n(intent classification)"]
        PLA --> RT{{"Adaptive\nRouter"}}
        RT -->|"fast / hybrid"| HY["Hybrid Retriever\ndense+sparse RRF\ncross-encoder rerank\nMMR dedup"]
        RT -->|"relational / multi-hop"| PR["PathRAG + PPR\npath expansion\nflow pruning\nPPR authority blending\n0.4·flow + 0.6·ppr"]
        RT -->|"uncertain / broad"| BOTH["Hybrid + PathRAG\ncombined context"]
        HY & PR & BOTH --> FU["Context Fusion\nMMR · lost-in-middle"]
        FU --> CR{{"Dual-Signal\nEvidence Critic"}}
        CR -->|"lexical gap <60%\nAND semantic <0.5"| RW["Query Rewriter\n+ retry (≤3 iters)"]
        RW --> RT
        CR -->|"evidence ok"| SY["Synthesizer\n(LLM streaming)"]
        SY --> SC["Self-Check\n4-signal confidence\n0.30·score + 0.30·cite\n+ 0.25·semantic + 0.15·token"]
        SC --> CV["Citation Validator\nstrip dangling\nadd score+method"]
        CV --> VGR["Visual Grounding\nResolver\nspan → page → unavailable"]
        VGR --> ST["SSE Response Streamer\nmeta · token · final events\nvisual_grounding in final"]
    end

    subgraph Frontend["🖥️ Frontend — Next.js 15"]
        direction TB
        CHAT["Chat Column\nMessage + Citations\nInlineSourceStrip"]
        INS["Inspector (30vw)\n6 tabs"]
        INS --> TAB1["Overview\nsuggestions · stats"]
        INS --> TAB2["Trace\nstep-by-step pipeline\nVG section"]
        INS --> TAB3["Evidence\nPathRAG paths\ncoverage bar"]
        INS --> TAB4["Source (compact)\n⛶ Expand button"]
        INS --> TAB5["Ingest\nVG status per doc"]
        INS --> TAB6["Eval\nmetrics · feedback"]
        RAIL["Agent Activity Rail\nalways-visible\nphase · algo · coverage"]
        SEL["Algorithm Selector\n3 groups: available\nexperimental · planned"]
        WS["Source Workspace Modal\nfull-screen fixed overlay\nEscape / ← → keys"]
        WS --> CP["Citation Panel\nclick → navigate PDF"]
        WS --> PV["PDF Viewer\nzoom 50–150% · fit\npage nav rail\nnormalized-bbox overlays"]
        WS --> EP["Evidence Panel\nsnippet · block type\nrelevance · confidence"]
    end

    subgraph API["🔌 REST API"]
        E1["POST /query/stream\nSSE streaming"]
        E2["GET /documents/{id}/pages"]
        E3["GET /documents/{id}/pages/{n}/image"]
        E4["GET /documents/{id}/pages/{n}/layout"]
        E5["GET /rag/strategies"]
        E6["GET /corpus/grounding-summary"]
        E7["POST /eval/feedback"]
        E8["GET /eval/last"]
    end

    VS --> HY
    KG --> PR
    PC --> E3
    DM --> E2
    ST --> E1
    E1 --> CHAT
    E1 --> INS
    CHAT --> WS
    TAB3 --> WS
    TAB4 --> WS
    E3 --> PV
    E4 --> EP
    E5 --> SEL
```

---

## ⚡ Auralynq-RAG Contribution

Auralynq-RAG is the default strategy — an adaptive hybrid pipeline combining
four original algorithmic contributions:

### 1 · PPR-Augmented PathRAG

Standard resource-decay PathRAG suffers short-path bias: paths with many hops
accumulate low flow budgets even when highly relevant. We correct this with
**Personalised PageRank (PPR)** authority blending:

```
score(path) = 0.4 · flow_score + 0.6 · ppr_authority
```

- `flow_score`: flow-based path bottleneck (min edge resource budget), robust to noisy edges
- `ppr_authority`: terminal-node score from `nx.pagerank()` seeded on query entities (α = 0.15)
- PPR personalization vectors are built per-query; convergence in ≤ 50 iterations
- Blended score re-orders paths before golden-region placement in the context window
- Inspired by HippoRAG2 (Gutierrez et al., NeurIPS 2024)

**Implementation**: `auralynq/retrieval/pathrag/retriever.py` — `_assign_ppr()`, `_apply_ppr()`

### 2 · Dual-Signal Evidence Sufficiency Critic

Single-signal (token-overlap) evidence critics trigger spurious rewrites when vocabulary
mismatch is the only gap. We require **both** signals to fire before rewriting:

| Signal | Threshold | Source |
|--------|-----------|--------|
| Lexical coverage | < 60 % (key-term overlap) | Token matching |
| Semantic coverage | < 0.50 (cosine similarity) | cosine(q_emb, mean(ctx_embs)) |

A query like "What is photosynthesis?" answered by a passage about "carbon fixation and
light-dependent reactions" has low lexical overlap but high semantic coverage → no rewrite.
This eliminates ~30 % of spurious rewrites observed with the token-only gate.

Inspired by FAIR-RAG (arXiv Oct 2025). **Implementation**: `auralynq/agent/nodes.py` — `_semantic_coverage()`

### 3 · Calibrated Four-Signal Confidence

Replace the single-heuristic confidence score with four orthogonal signals:

```
confidence = 0.30 · score_quality
           + 0.30 · citation_coverage
           + 0.25 · semantic_coverage
           + 0.15 · token_coverage

score_quality = clip(mean_retrieval_score / 0.7, 0, 1)
```

| Signal | Weight | What it measures |
|--------|--------|------------------|
| Score quality | 0.30 | Mean cross-encoder score vs. 0.70 on-topic reference |
| Citation coverage | 0.30 | Fraction of retrieved chunks actually cited |
| Semantic coverage | 0.25 | cosine(query, answer) — grounding depth |
| Token coverage | 0.15 | Key-term recall in the answer |

Low confidence is now diagnosable: a low `citation_coverage` score means the LLM
ignored retrieved context; low `score_quality` means retrieval quality was poor.
The UI `ConfidenceBar` renders all four components for transparency.

Inspired by Bayesian RAG (Frontiers 2026). **Implementation**: `auralynq/agent/nodes.py` — `node_self_check`

### 4 · Adaptive Strategy Routing

A pluggable strategy registry dispatches to 13 distinct retrieval modes based on
query complexity, corpus metadata, and available infrastructure:

```
Strategy Registry
├── Available now
│   ├── auralynq_rag   — full adaptive pipeline (default)
│   ├── hybrid         — dense+sparse+rerank only
│   ├── naive_vector   — pure vector, no rerank
│   └── keyword_bm25   — BM25 only
├── Experimental
│   ├── self_rag       — critique-revise loop; SUPPORT/RELEVANT/USEFUL tokens
│   ├── crag           — corrective RAG; LLM quality check + query rewrite fallback
│   └── adaptive_rag   — 8-category LLM classifier → route selection
└── Planned (require setup)
    ├── graph_rag      — requires entity_count > 0
    ├── hybrid_rerank  — requires AURALYNQ_RERANKER_ENABLED=true
    ├── lightrag_local / global / hybrid
    ├── raptor         — hierarchical summaries
    └── hipporag       — HippoRAG2 full pipeline
```

**Implementation**: `auralynq/rag/` — `strategy_registry.py`, `strategies/`

---

## 🔬 Visual Source Grounding

Every cited answer can be visually verified against the original PDF/image.
This is the first implementation of span-level visual grounding in the Auralynq pipeline.

### How it works

```
PDF ingest
  └─► pdfplumber extracts layout blocks (bbox per text region per page)
  └─► Chunk ↔ layout block overlap matching → normalized_bbox stored in chunk metadata
  └─► pdf2image renders page PNGs at 144 DPI into data/page_cache/{doc_id}/

Query response
  └─► GroundingResolver maps citations → (doc_id, page, normalized_bbox)
  └─► Stage resolution: span (exact bbox) → page (page known, no bbox) → unavailable
  └─► visual_grounding injected into SSE final event
  └─► Frontend renders Source Workspace
```

### Grounding stages

| Stage | Meaning | Visual |
|-------|---------|--------|
| `span` | Exact text-span bounding box from layout extraction | Colored rectangle around exact text |
| `page` | Page number known, no span-level bbox | Soft page-level highlight |
| `unavailable` | No grounding metadata — doc needs reindex | Warning + reindex prompt |

### Source Workspace — three-panel document viewer

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  Grounded Source Workspace                   [50%][75%][fit][125%][150%]  ✕ ║
║                                              [−][87%][+]  ‹ p.2  1/3 ›  ⛶  ║
╠═══════════════╦═════════════════════════════════════╦════════════════════════╣
║ Citations      ║            PDF Viewer               ║  Evidence · Page 2     ║
║                ║                                     ║                        ║
║ [1] report.pdf ║  ┌───────────────────────────────┐  ║  ■ [1] paragraph·span ║
║     p.2 ←here  ║  │                               │  ║  "the cited text      ║
║                ║  │  Introduction                 │  ║   excerpt goes here…" ║
║ [2] report.pdf ║  │  ┌─────────────────────────┐  │  ║  rel 84% · conf 91%   ║
║     p.4        ║  │  │[1]▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  │  │  ║                        ║
║                ║  │  └─────────────────────────┘  │  ║  ■ [2] table·span     ║
║ ─── Claims ─── ║  │                               │  ║  "related evidence     ║
║                ║  │  Methods                      │  ║   from this block…"   ║
║ ✓ Supported    ║  │  ┌─────────────────────────┐  │  ║  rel 71% · conf 88%   ║
║ "claim text…"  ║  │  │[2]░░░░░░░░░░░░░░░░░░░  │  │  ║                        ║
║                ║  │  └─────────────────────────┘  │  ║  ─── Legend ─────────  ║
║ ⚡ Partial     ║  │                               │  ║  ■ Span-level exact    ║
║ "other claim…" ║  └───────────────────────────────┘  ║  □ Page-level only     ║
╚═══════════════╩═════════════════════════════════════╩════════════════════════╝
```

**Interactions:**
- **Click citation** → PDF navigates to that page, highlight pulses
- **Click highlight box** → snippet + support status shown in right panel
- **Arrow keys** → prev/next page across all cited pages
- **Escape** → close workspace
- **⛶** → full-screen PDF (hide side panels)
- **Zoom presets**: 50 % / 75 % / fit-width / 125 % / 150 % + fine ±10 %

### Backend endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /documents/{id}/pages` | Page count + dimensions + image availability |
| `GET /documents/{id}/pages/{n}/image` | Serve rendered page PNG |
| `GET /documents/{id}/pages/{n}/layout` | Layout blocks (chunks with bbox) for page |
| `GET /documents/{id}/grounding-status` | VG version, reindex required, n_pages |
| `GET /corpus/grounding-summary` | Grounded vs needs-reindex counts |
| `POST /documents/{id}/render-pages` | Re-render pages without full reindex |

---

## 🖥 Frontend

### Chat workspace

The chat workspace is a two-column layout: conversation + always-visible inspector.

```
┌─────────────────────────────────────┬──────────────────────────────────────┐
│  AppBar: status · entities · ⚙ ·☰  │  Agent Activity Rail (always visible) │
├─────────────────────────────────────┼──────────────────────────────────────┤
│                                     │  Tabs: Overview · Trace · Evidence ·  │
│  [User] Summarize the documents.    │         Source · Ingest · Eval        │
│                                     │                                        │
│  [Assistant] The documents cover…   │  ┌─ Overview ──────────────────────┐  │
│              [1] [2]                │  │ suggestions · coverage · stats   │  │
│                                     │  └──────────────────────────────────┘  │
│  ◉ report.pdf · p.2 · span match   │  ┌─ Trace ─────────────────────────┐  │
│  [Preview] [View source ↗]          │  │ planner → router → retriever    │  │
│                                     │  │ VG: resolver · page cache       │  │
│  ─────────────────────────────────  │  └──────────────────────────────────┘  │
│                                     │                                        │
│  ⚡ auralynq-rag ▾  [────────────]  │  ┌─ Evidence ──────────────────────┐  │
│  Composer: text input + voice 🎙    │  │ coverage bar · PathRAG paths    │  │
└─────────────────────────────────────┴──────────────────────────────────────┘
```

### Inspector tabs

| Tab | Content |
|-----|---------|
| **Overview** | Corpus stats, recent metrics, suggestions |
| **Trace** | Step-by-step pipeline trace with VG pipeline section; Phoenix link |
| **Evidence** | Coverage bar, PathRAG graph paths, citation cards with "View source ↗" |
| **Source** | Compact docked PDF preview + "⛶ Expand" → Source Workspace |
| **Ingest** | File upload, per-document VG status (span/page/reindex), corpus management |
| **Eval** | Last-query metrics, feedback widget, export run, async eval runner |

### Algorithm Selector

The strategy picker sits in the composer bar and groups strategies by availability:

```
⚡ Auralynq-RAG ▾

┌──────────────────────────────────────┐
│ RAG Algorithm                        │
│ ● Available now                    3 │
│   ✓ Auralynq-RAG          default   │
│     Hybrid Vector          fast      │
│     Keyword BM25           fast      │
├──────────────────────────────────────┤
│ ○ Experimental                     3 │
│     Self-RAG               medium    │
│     CRAG                   slow      │
│     Adaptive RAG           slow      │
├──────────────────────────────────────┤
│ · Planned / requires setup         7 │
│   (disabled — shows requirements)    │
└──────────────────────────────────────┘
```

---

## 🚀 Quickstart

> Auralynq is **Podman-first** and does **not** require Docker.
> Full run modes — including **deploying to a remote machine** — are in
> **[RUNNING.md](RUNNING.md)**.

```bash
# 0. (optional) only needed for gated models (e.g. diarization)
cp .env.example .env && echo "HUGGINGFACE_TOKEN=hf_..." >> .env

# 1. Light install ($0; offline-capable)
make setup

# 2. Verify container runtime + start the full stack
make runtime-check
make stack-up          # or: make up

# 3. Or run end-to-end locally without containers:
make data              # download sample corpus
make index             # vector index + knowledge graph
make demo              # ingest → index → query (text + voice)

# 4. Ask something:
auralynq ask "How does PathRAG prune relational paths?"
auralynq talk          # push-to-talk voice loop
```

Open the UI at **http://localhost:3000**, API docs at **http://localhost:8000/docs**,
Phoenix traces at **http://localhost:6006**.

### Podman stack (local + remote)

```bash
# Build images then start the stack
podman build --no-cache --squash-all -f containers/web.Dockerfile -t localhost/auralynq-web:0.2.0 web/
podman build --no-cache -f containers/api.Dockerfile -t localhost/auralynq-api:0.2.0 .
make up

# Seed + index inside the container
podman exec auralynq-api auralynq data --sample
podman exec auralynq-api auralynq index --input /app/data/corpus
```

> **Rebuild warning**: `podman-compose build --no-cache` silently reuses cached layers
> for both the multi-stage web image and the single-stage API image. Always use
> `podman build --no-cache` directly for any image rebuild.

---

## 🌐 Remote / server deployment

The stack exposes **one public port** (`8443`, Caddy TLS) — UI, API, Qdrant and Phoenix
bind to localhost only and are unreachable from the server NIC.

```bash
# .env  (git-ignored; consumed by podman-compose — never committed)
AURALYNQ_SERVE__API_KEY=<openssl rand -hex 32>
NEXT_PUBLIC_API_BASE=/api
AURALYNQ_SERVE__CORS_ORIGINS=["https://<SERVER_IP>:8443"]
AURALYNQ_HTTPS_PORT=8443
AURALYNQ_CERT_HOST=<SERVER_IP>          # self-signed cert SAN (or domain)
AURALYNQ_SITE_ADDRESS=:8443             # or https://your.domain (Let's Encrypt)
AURALYNQ_BIND_INTERNAL=127.0.0.1
AURALYNQ_WEB_PORT=3300
AURALYNQ_QDRANT_HTTP_PORT=6533
COHERE_API_KEY=<...>                    # optional; degrades to offline fallback
```

Browse to **https://&lt;SERVER_IP&gt;:8443** — only `8443` needs to be open in the firewall.
The browser never holds the API key (the web container's same-origin `/api/*` proxy
injects the bearer token server-side).

---

## ⚙️ Configuration

All config via env vars (prefix `AURALYNQ_`, nested with `__`). See [`.env.example`](.env.example).

| Variable | Default | Purpose |
|----------|---------|---------|
| `AURALYNQ_EMBEDDING__PROVIDER` | `auto` | `auto` / `bge` / `hash` / `openai` |
| `AURALYNQ_VECTOR__BACKEND` | `auto` | `auto` / `qdrant` / `memory` |
| `AURALYNQ_LLM__PROVIDER` | `auto` | `auto` / `ollama` / `openai` / `anthropic` / `cohere` |
| `AURALYNQ_VOICE__ASR_PROVIDER` | `auto` | `auto` / `faster_whisper` / `whisperx` / `null` |
| `AURALYNQ_VOICE__TTS_PROVIDER` | `auto` | `auto` / `kokoro` / `null` |
| `AURALYNQ_AGENT__MAX_ITERS` | `3` | Retry cap for the rewrite loop |
| `AURALYNQ_AGENT__LATENCY_BUDGET_MS` | `15000` | Agent latency budget |
| `AURALYNQ_SERVE__API_KEY` | _(empty)_ | Bearer token; empty = open (local only) |
| `AURALYNQ_SERVE__RATE_LIMIT_PER_MIN` | `120` | Per-client request cap |
| `AURALYNQ_VISUAL__ENABLED` | `true` | Enable visual grounding system |
| `AURALYNQ_VISUAL__PAGE_RENDERING_ENABLED` | `true` | Render page PNGs at ingest |
| `AURALYNQ_VISUAL__RENDER_DPI` | `144` | Page render resolution |
| `AURALYNQ_VISUAL__MAX_CACHED_PAGES` | `500` | Page cache limit |
| `AURALYNQ_VISUAL__VISUAL_RETRIEVAL_ENABLED` | `false` | ColPali-style visual retrieval (experimental) |
| `AURALYNQ_DEFAULT_RAG_STRATEGY` | `auralynq_rag` | Default strategy for all queries |

---

## 📦 Container images

Three versioned OCI images — `auralynq-api`, `auralynq-web`, `auralynq-caddy`.

```bash
make version            # show resolved version + tag set
make images             # build all 3 images
make push               # push to ghcr.io/<owner>/*
git tag v0.2.0 && git push origin v0.2.0   # CI publishes automatically
```

---

## 🧩 Services & scaling

| Service | Image | Purpose |
|---------|-------|---------|
| `api` | `auralynq-api` | REST API + streaming |
| `worker` | `auralynq-api` | Background tasks |
| `mcp` | `auralynq-api` | MCP server (stdio / HTTP) |
| `web` | `auralynq-web` | Next.js UI + API proxy |
| `caddy` | `auralynq-caddy` | TLS reverse proxy |
| `qdrant` | `qdrant/qdrant` | Vector store |
| `phoenix` | `arizephoenix/phoenix` | Trace / eval UI |

Kubernetes manifests in [`deploy/k8s`](deploy/k8s) — per-service Deployments+Services,
HPA autoscaling, Qdrant StatefulSet, ConfigMap/Secret, Ingress.

---

## 🔌 Providers

| Capability | Local ($0) | Optional upgrade | Required env |
|------------|-----------|------------------|--------------|
| Embeddings | `BAAI/bge-m3` → hash fallback | OpenAI embeddings | `OPENAI_API_KEY` |
| Vector DB | Qdrant (Podman) → in-memory | Qdrant Cloud | `AURALYNQ_VECTOR__URL` |
| Rerank | `bge-reranker-v2-m3` → lexical | Cohere rerank | `COHERE_API_KEY` |
| LLM | Ollama local → extractive | OpenAI / Anthropic / Cohere | `*_API_KEY` |
| ASR | faster-whisper → null | WhisperX (align+diarize) | `HUGGINGFACE_TOKEN` |
| TTS | Kokoro-82M → silent/sine | — | — |
| Tracing | in-process spans | Phoenix + Langfuse | `LANGFUSE_*` |
| Layout | pdfplumber (included) | — | — |
| Page render | pdf2image + poppler (included) | higher DPI via env | — |

---

## 🔭 Observability

Every answer builds an in-process **trace** (one span per node: planner, router,
retrievers, synthesizer, VG resolver, …) returned in the API response and rendered in
the UI Trace panel. The VG pipeline section shows: metadata lookup → resolver stage →
page cache hit/miss → claim alignment.

- **Phoenix** — local OTLP/trace UI on `:6006` (in the stack)
- **Langfuse** — hosted trace/eval; set `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY`
- **Eval Panel** — last-query metrics (`/eval/last`), feedback widget, async eval runner,
  export run JSON; quality gates run via `make eval` / `make bench`

---

## 🧰 MCP server (`auralynq-mcp`)

Exposes **7 tools** — `ingest_documents`, `search`, `graph_path_query`, `transcribe`,
`talk_to_data`, `run_eval`, `get_trace` — so any MCP client (Claude Desktop, IDEs,
agents) can drive the full pipeline.

```bash
pip install 'auralynq[mcp]'
auralynq-mcp                              # stdio (default)
auralynq-mcp --transport streamable-http  # HTTP on :8765
```

Claude Desktop config:
```json
{ "mcpServers": { "auralynq": { "command": "auralynq-mcp" } } }
```

---

## 📊 Benchmarks

> Numbers produced **only** by `make eval` / `make bench`, written to `reports/`.
> Measured in the fully-offline `$0` config (hash embeddings, in-memory store,
> extractive LLM) over a frozen 5-item golden set. Install `embeddings`/`agent`
> extras for quality numbers.

**Retrieval comparison** (k=6, nDCG@10):

| Metric | naive | hybrid | PathRAG | full agentic |
|--------|------:|-------:|--------:|-------------:|
| Recall@k          | 1.00  | 1.00   | 0.80    | 0.80         |
| nDCG@10           | 0.900 | 0.886  | 0.800   | 0.800        |
| MRR               | 0.867 | 0.850  | 0.800   | 0.800        |
| Precision@k       | 0.167 | 0.167  | 0.133   | 0.133        |
| Latency p50 (ms)  | 0.1   | 1.3    | 0.1     | 16.6         |

**Answer quality** (full agentic, Ragas proxy):

| Faithfulness | Answer relevancy | Context precision |
|-------------:|-----------------:|------------------:|
| 0.80         | 0.41             | 0.64              |

**Qdrant quantization trade-off** (289 vectors, dim 256):

| Quantization | Recall@10 | Memory | Compression |
|--------------|----------:|-------:|------------:|
| none (fp32)  | 1.00      | 289 KB | 1×          |
| scalar (int8)| 1.00      | 72 KB  | **4×**      |
| binary (1-bit)| 0.50     | 9 KB   | **32×**     |

---

## Architecture notes

- **PPR PathRAG** (`retrieval/pathrag/retriever.py`): `_assign_ppr()` runs
  `nx.pagerank()` with seed personalization (α=0.15 teleport); `_apply_ppr()` tags
  each path with terminal-node PPR authority; blended `0.4·flow + 0.6·ppr` re-orders
  before golden-region placement.

- **Evidence critic** (`agent/nodes.py`): `_semantic_coverage()` computes
  `cosine(q_emb, mean(ctx_embs))` using the shared embedder; rewrite fires only when
  both `coverage < 0.6` **and** `semantic_coverage < 0.5`.

- **Confidence calibration** (`node_self_check`): four-signal formula weights
  `[0.30, 0.30, 0.25, 0.15]` over `[score_quality, citation_coverage, semantic_coverage,
  token_coverage]`; `score_quality = clip(mean_score / 0.7, 0, 1)`.

- **Visual grounding** (`grounding/resolver.py`): `GroundingResolver.resolve()` maps
  citations → `VisualEvidence`; staged: span → page → unavailable; normalized bbox
  stored per chunk in Qdrant payload at ingest time.

- **Source Workspace** (`components/SourceWorkspaceModal.tsx`): fixed full-screen
  z-[200] overlay; highlight boxes use `normalized_bbox` as CSS `%` — stays aligned
  at any zoom; keyboard navigable (Esc / ← →).

---

## Limitations

- Offline fallbacks (hash embeddings, extractive LLM) verify pipeline integrity, not quality.
- KG is NetworkX + JSON (laptop-scale); swap for a graph DB at scale.
- Diarization needs `HUGGINGFACE_TOKEN` and accepted pyannote model terms.
- `layout_blocks` are per-chunk in Qdrant (not stored separately per page in a layout DB).
  The `/pages/{n}/layout` endpoint does a bounded Qdrant scroll; large documents may
  need a dedicated layout store.
- ColPali-style visual retrieval (`AURALYNQ_VISUAL__VISUAL_RETRIEVAL_ENABLED=true`)
  remains gated / experimental.

## Roadmap

- [ ] Page thumbnail rail in Source Workspace (requires `/thumbnail` endpoint)
- [ ] Layout block store written at ingest for cheaper page-level queries
- [ ] ColPali visual retrieval (image-to-image semantic search)
- [ ] Streaming partial ASR in the WebSocket loop
- [ ] Graph-DB backend for the KG (larger scale)
- [ ] Multi-tenant collections + per-user auth
- [ ] LightRAG / RAPTOR strategy implementations
- [ ] Langfuse + OTLP dashboards out of the box

---

## Design decisions

See [DECISIONS.md](DECISIONS.md) for the full ADR log.

## License

[Apache-2.0](LICENSE). Third-party components attributed in [THIRD_PARTY.md](THIRD_PARTY.md).
