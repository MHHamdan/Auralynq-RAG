# Product & UX Competitor Audit

Internal working document. Goal: make Auralynq look and feel like a serious
open-source agentic voice-RAG + PathRAG platform with **better groundedness,
observability, and UX** than typical "chat-with-your-docs" demos. We do **not**
copy any design; this audit only frames the quality bar and the concrete
improvements we ship.

Last updated: 2026-06-03 (post PR #16).

---

## 1. What the field does well

| Tool | What it does well (visually / UX) | Where it's weak |
|------|-----------------------------------|-----------------|
| **Dify** | Clean, light, high-contrast app shell; "Apps" gallery with strong empty states; visual prompt/workflow builder; explicit model/provider chips. | RAG transparency is shallow — you rarely see *why* an answer was grounded. |
| **RAGFlow** | Best-in-class **chunk visualization**: shows the parsed document, the exact retrieved chunk, page image, and bounding boxes. Citations point back to the source region. | Heavy, document-centric; weak on agentic/multi-hop reasoning display. |
| **AnythingLLM** | Friendly onboarding, workspace metaphor, drag-and-drop ingestion with live progress, clear "documents in this workspace" panel. | Observability is minimal; no trace/eval story. |
| **Langfuse** | Gold standard for **traces**: waterfall spans, latency/cost/token per step, nested generations, score/eval overlays, session grouping. | It's a backend/observability tool, not an answer UI — no end-user grounding view. |
| **Arize Phoenix** | Strong **span/trace explorer**, embeddings/retrieval evaluation, RAG relevance heatmaps, "did retrieval find the right context" diagnostics. | Developer-facing; not a product surface for end users. |
| **Flowise** | Node-graph pipeline builder makes the RAG flow *legible* — you can see Upload → Split → Embed → Retrieve → LLM as a graph. | The runtime answer view is generic chat; little grounding. |
| **Open WebUI (RAG)** | Polished chat, citations inline, model switcher, light/dark themes, keyboard-first. | Retrieval is a black box; no path/graph reasoning. |
| **LlamaIndex / LlamaCloud** | Clear mental model: parse → index → retrieve → synthesize; good "retrieved nodes with score" inspector; query-engine observability. | Mostly SDK/notebook; the hosted UI is utilitarian. |

### Patterns worth internalizing
- **Grounding is a first-class view, not a footnote.** RAGFlow/Phoenix prove that
  showing *the evidence and the score* is what builds trust.
- **The pipeline should be legible.** Flowise/LlamaIndex make the stages explicit
  (Upload → Parse → Index → Retrieve → Rerank → Reason → Cite → Observe).
- **Traces sell the product.** Langfuse's waterfall (status · duration · tokens ·
  cost · provider per step) reads as "serious infrastructure."
- **Honest refusal beats confident hallucination** — but only if the refusal
  *explains itself*. None of the competitors do abstention well; this is our wedge.
- **Provider/model transparency.** Dify/Open WebUI always show which model/provider
  answered. We already have `health.providers`; surface it everywhere.

---

## 2. How they explain RAG workflows

- **Stage strips / node graphs** (Flowise, Dify, LlamaIndex): a left-to-right
  pipeline so a first-timer understands what happens to their data.
- **Live status** (AnythingLLM): ingestion progress, chunk counts, index size.
- **Retrieved-context inspectors** (Phoenix, LlamaIndex): the actual chunks with
  relevance scores, so retrieval quality is auditable.

**Auralynq angle:** we have a *richer* pipeline than most — Upload → Parse →
Index → **Retrieve → Graph-expand (PathRAG) → Rerank → Sufficiency-check →
Reason → Cite → Observe**. The graph-expansion and sufficiency-check steps are
differentiators almost nobody shows. Make them visible.

---

## 3. How they show traces, evidence, citations, evaluations

- **Traces:** Langfuse/Phoenix waterfalls — span name, status, start, duration,
  tokens, cost, model. Nested spans for retrieval → rerank → generation.
- **Evidence:** RAGFlow chunk cards with source + page + score; Phoenix
  retrieval-relevance per chunk.
- **Citations:** inline `[n]` markers that resolve to a source + locator
  (Open WebUI, Perplexity-style).
- **Evaluations:** Langfuse/Phoenix attach scores (faithfulness, relevance) to
  traces; Ragas-style metrics surfaced as dashboards.

**Auralynq already has the raw material:** in-process `Trace` spans, PathRAG
`path_evidence` (nodes/relations/reliability), citations with source+locator+span,
and a Ragas/eval report endpoint. The gap is **presentation**, not data.

---

## 4. What Auralynq does differently (our positioning)

1. **Agentic *voice* RAG** — talk to your data, not just type. ASR/TTS provider
   transparency is a first-class status item.
2. **PathRAG reasoning** — graph paths with relation types and reliability scores,
   shown as evidence. This is multi-hop reasoning made visible.
3. **Trustworthy abstention** — when evidence is insufficient we *refuse and
   explain*: detected entities, retrieval route attempted, top snippets found, why
   they were insufficient, and corpus-aware suggestions. Nobody does this well.
4. **Local-first, $0 default, honest providers** — `/health` and `/api/status`
   never lie about local-vs-upgraded execution.
5. **Observability as a product feature** — Agent Trace with per-step status /
   latency / provider, plus a summary dashboard (total/retrieval/generation
   latency, evidence coverage, confidence, hallucination-risk flag, abstention
   reason, fallback used). Optional "Open in Phoenix" link when Phoenix runs.

---

## 5. Practical checklist (this PR)

Backend — structured contracts so the frontend never guesses:
- [x] `GET /health`, `GET /api/status` (providers + index + corpus + tracing).
- [x] `GET /api/corpus/summary` — doc count, titles, source types, top entities,
      last-indexed time.
- [x] `GET /api/suggestions` — corpus-aware example questions (no stale geography
      chips unless the corpus supports them).
- [x] `GET /api/observability/summary` — request/latency counters + tracing target.
- [x] `POST /api/query` returns: `status`, `route`, `evidence`/`contexts`,
      `citations`, `path_evidence`, `insufficient_evidence_reason`,
      `suggested_questions`, `detected_entities`, `evidence_coverage`,
      `trace_steps`, `provider_status`, `warnings`.

Frontend — make the data legible:
- [x] Light / Dark / Comfort (high-contrast) themes via CSS variables, persisted
      to `localStorage`, switcher always visible.
- [x] Corpus-aware suggestion chips from `/api/suggestions` (with graceful
      empty-corpus state).
- [x] Rich **insufficient-evidence** card: reason + detected entities + route +
      retrieved snippets + suggested questions + "ingest documents" CTA.
- [x] **Evidence** panel: coverage meter, separated vector / graph / reranker /
      citation sections, collapsible, per-snippet score + source/locator.
- [x] **Agent Trace** panel: per-step status / duration / provider / counts +
      summary dashboard (latencies, coverage, confidence, abstention, fallback)
      + optional "Open Phoenix" link.
- [x] **Ingest** panel: drag-and-drop, supported types, progress, indexed count,
      last-indexed time, sample questions after indexing, reindex hint.

Quality gates:
- [x] Backend tests for insufficient-evidence shape, corpus-aware suggestions,
      trace-step serialization, evidence-coverage calculation.
- [x] Lint, typecheck, frontend build, container build, live smoke on port 2002.

### Explicitly *not* doing
- No design cloning. No marketing-only cosmetic churn. No removal of the honest
  "not enough evidence" behavior — we make it *more* trustworthy, never chattier.
</content>
</invoke>
