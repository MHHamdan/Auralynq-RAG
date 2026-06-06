# Root-Cause Audit: Corpus Deletion & Layout Issues

**Branch:** fix/corpus-delete-and-responsive-commercial-ui  
**Date:** 2026-06-06

---

## 1. Corpus Persistence Map

| Layer | Path | Cleared by prior `clear`? |
|---|---|---|
| Vector embeddings (memory) | `data/index/memory_store/dense.npy` | Only via CLI `--rebuild` |
| Chunk metadata (memory) | `data/index/memory_store/chunks.json` | Only via CLI `--rebuild` |
| Knowledge graph | `data/index/graph.json` | Only via CLI `--rebuild` |
| Last ingested sidecar | `data/index/last_ingested.json` | Not cleared |
| Ingest manifest (idempotency) | `data/storage/ingest_manifest.json` | Not cleared |
| Qdrant collection | remote server `auralynq` collection | Only via CLI `--rebuild` |
| Corpus summary cache | in-process dict `_cache` in `serving/corpus.py` | `invalidate_corpus_cache()` called after ingest, never after delete |
| Suggestions cache | computed on demand from summary | Same as above |
| Upload files | `data/storage/uploads/` | Deleted **immediately after indexing** via `dest.unlink()` — no files remain |
| Voice temp files | `data/storage/voice_in/`, `data/storage/ws_voice/` | Deleted per-request |
| TTS output | `data/storage/tts_out.wav` | Overwritten per-request |
| Frontend localStorage | `auralynq.chat.v1` in browser | Never cleared on deletion |
| eval/bench reports | `reports/eval_report.json`, `reports/bench_report.json` | Never cleared |

**Root cause of "still shows 25 documents/2191 vectors/39 entities after deletion attempt":**  
No deletion endpoint exists. The corpus can only be rebuilt/cleared via the CLI command `auralynq index --rebuild`, which calls `store.clear()` + re-indexes. There is no HTTP endpoint for deletion at all.

---

## 2. Current Deletion Flow

**Existing endpoint(s):** None. No `/corpus/delete`, `/corpus/clear`, or similar endpoint.

**Existing frontend button(s):** None. No delete or clear button in the UI.

**Deletion mechanics:**
- `store.clear()` on `MemoryStore`: wipes in-process dict/arrays, overwrites `dense.npy` + `chunks.json` on next `save()`
- `store.clear()` on `QdrantStore`: calls `client.delete_collection()` — drops the entire collection
- Neither clears the ingest manifest, last_ingested sidecar, or graph.json independently
- The manifest is never cleared, causing re-index to skip all known files (idempotency bug if graph.json is deleted but manifest remains)
- `invalidate_corpus_cache()` is only called after ingest, not after deletion — stale 30s TTL applies

**What was not cleared:**
- Ingest manifest (so re-index after a clear skips all files as "unchanged")
- `last_ingested.json` (shows stale "last document" after clear)
- Frontend localStorage `auralynq.chat.v1` (old conversations with stale corpus context persist)
- Suggestions/topics (derived from cached summary, won't refresh until cache TTL expires)

---

## 3. Current Routing Flow

**Intent classification:** Entirely client-side via `isInventoryQuestion()` in `web/lib/format.ts`.

**Backend routing:** `auralynq/retrieval/router.py` only classifies query complexity (`fast` / `graph` / `hybrid`). No corpus management intent exists.

**Why corpus-management questions route to RAG:**  
If the frontend's `isInventoryQuestion()` heuristic misses a question (e.g. "how many documents do I have so far?", "can I remove the last document?", "how do I delete them?"), the question goes to `/query/stream` which runs full RAG. RAG retrieves semantically similar chunks from the indexed corpus and returns those as citations — completely wrong for management questions.

**Why follow-up questions lose context:**  
The frontend checks each question independently via `isInventoryQuestion()`. After "can I delete documents?", a follow-up "how?" is standalone and matches no inventory pattern, so it goes to RAG.

**Where retrieval should be skipped:**  
At the backend query handler, before `answer_question()` is called. A backend intent classifier running on the raw question text can intercept management intents before any retrieval happens.

---

## 4. Layout Audit

**Current page width constraints:**  
```jsx
// chat/page.tsx line 309
<div className="mx-auto grid w-full max-w-[1600px] flex-1 ...">
```
`mx-auto` + `max-w-[1600px]` centers the app in a 1600px box, leaving up to 320px blank on each side on a 1920px display.

**Inspector behavior:**  
```jsx
lg:grid-cols-[minmax(0,1fr)_400px]
```
Inspector column is always exactly 400px regardless of viewport width. On a 1024px laptop, the chat area gets only ~624px. On a 1440px desktop, 1040px for chat and 400px for inspector — leaving ~560px chat width after padding, which is narrow.

**When inspector is hidden (showPanel=false):**
```jsx
className={`... lg:flex ${showPanel ? "..." : "hidden"}`}
```
`hidden` in Tailwind is `display: none` (no `!important` in Tailwind v3). But `lg:flex` is in a media query. The generated CSS file places responsive utilities after base utilities, so `lg:flex` overrides `hidden` at the lg breakpoint. **However**, initial `showPanel=false` means the inspector is rendered in the DOM as `hidden`, not `lg:flex` — because Tailwind processes them alphabetically and `hidden` appears before `lg:flex` in the CSS output. This is the source of the empty right side: `hidden` takes effect even at lg+ breakpoints due to CSS ordering.

**Hardcoded dimensions:**  
- Inspector: `400px` fixed
- Chat scroll area: `max-w-3xl` (768px) inner limit
- Composer: `max-w-3xl` outer limit
- EmptyConversation: `max-w-xl` suggestion area, `max-w-md` subtitle

**Contrast/readability:**  
- Dark theme: strong, good contrast
- Light theme: `--c-text-3: 71 85 105` on white background ≈ 4.6:1, borderline
- Comfort theme: warm sepia, readable but low saturation makes status colors (ok/warn/bad) hard to distinguish

**CSS files responsible:**  
- `web/app/globals.css` — design tokens, base styles
- `web/tailwind.config.ts` — theme extension
- `web/app/chat/page.tsx` — main layout grid
- `web/components/landing/Hero.tsx`, `Features.tsx`, etc. — landing page layout

---

## 5. Summary of Root Causes

1. **No deletion endpoint** → corpus data cannot be cleared via the API
2. **Manifest not cleared** → re-index after manual clear skips all files
3. **No backend intent classification** → management questions route to RAG
4. **`isInventoryQuestion()` client-only** → backend has no guardrail
5. **`hidden` overrides `lg:flex`** → inspector missing on desktop when `showPanel=false`
6. **Fixed 400px inspector + `max-w-[1600px]`** → wasted canvas on wide screens
7. **Corpus cache not invalidated on deletion** → stale summary after delete
8. **`last_ingested.json` not updated on deletion** → stale "last document" shown
