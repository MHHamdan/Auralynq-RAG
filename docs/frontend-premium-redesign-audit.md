# Auralynq — Frontend Premium Product Redesign Audit

> Branch: `feat/frontend-premium-product-redesign`
> Goal: make Auralynq read as a serious open-source product — not a demo —
> alongside Dify, RAGFlow, Langfuse, Phoenix, Flowise, Open WebUI, and the
> developer-platform bar set by Linear, Vercel, Supabase, Raycast, and Stripe.

Auralynq's identity, which every decision below serves:

> **Auralynq = local-first, voice-native, evidence-grounded, observable RAG.**

This is a reference-and-raise audit. We do **not** copy any product. We extract
the *principles* that make each one feel credible and apply them to our own
identity.

---

## 1. What to learn from each reference (and what not to copy)

### RAG / LLM-ops products

**Dify**
- *Learn:* confident node/pipeline visual language; capability cards with a
  single strong icon + one-line benefit; generous use of color to differentiate
  feature families.
- *Don't copy:* their busy multi-color marketing gradients and crowded nav.

**RAGFlow**
- *Learn:* "show the document evidence" as a first-class, central feature — the
  chunk/citation viewer is the hero, not a debug tab. Evidence is the product.
- *Don't copy:* dense table-heavy admin screens; we are answer-first.

**Langfuse**
- *Learn:* observability as a clean dashboard — a summary stat strip on top
  (latency, cost, tokens), then a trace timeline/waterfall with per-span status
  and duration. Calm, monochrome surface with a single accent.
- *Don't copy:* the full enterprise nav/sidebar density; we surface one trace.

**Arize Phoenix**
- *Learn:* span waterfall with latency bars, status pills, and drill-down. Trace
  steps read like a story (request → retrieve → rerank → generate).
- *Don't copy:* notebook-grade information density; we keep one readable trace.

**Flowise**
- *Learn:* approachable, friendly node aesthetic; clear "drag to build" cues.
- *Don't copy:* the canvas-builder paradigm — Auralynq is answer-centric, not a
  flow editor.

**Open WebUI**
- *Learn:* a focused, chat-first workspace with a sticky composer, model/mode
  selector inline, and a clean message rhythm. Voice and attach controls sit
  *in* the composer.
- *Don't copy:* the sometimes-cramped grey-on-grey contrast.

### Answer-layout references

**Perplexity**
- *Learn:* answer-first layout — the grounded answer is large and readable,
  citations are compact numbered chips inline and a clean source rail beside it.
  Sources feel trustworthy, not like footnotes.
- *Don't copy:* the ad/related-questions sprawl.

### Developer-platform bar (the quality target)

**Linear**
- *Learn:* ruthless typographic hierarchy, tight spacing rhythm, subtle depth
  (1px borders + soft shadow, not heavy glass), keyboard-first affordances shown
  subtly. Dark mode that is near-black with one cool accent.
- *Don't copy:* the all-purple brand — we keep teal/indigo identity.

**Vercel**
- *Learn:* high-contrast black/white, confident huge hero type, crisp cards with
  hairline borders, status dots done well. "Less but sharper."
- *Don't copy:* the stark monochrome — we want warmth + an evidence story.

**Supabase**
- *Learn:* developer-warm green accent on dark; honest product screenshots in
  hero; "open source" worn as a badge of trust; great empty states.
- *Don't copy:* the dashboard chrome density.

**Raycast**
- *Learn:* premium glass + gradient done *tastefully* (saturated but dark base,
  never washed out); delightful micro-interactions; command/keyboard polish.
- *Don't copy:* the macOS-skeuomorphic window framing everywhere.

**Stripe (developer pages)**
- *Learn:* gradient treatment that stays rich because it sits on a deep base;
  precise spacing; trust badges; the sense that every pixel is intentional.
- *Don't copy:* the enterprise breadth/marketing length.

**Synthesis — what makes all of these "serious":**
1. High contrast. Text is never washed out; secondary text still passes ~4.5:1.
2. A *deep* base (not pale) so gradients read as rich, not faded.
3. One confident accent identity, used sparingly.
4. Hairline borders + soft, low-spread shadows for depth — not heavy blur glass.
5. Strong type scale with real hierarchy (display → h2 → body → caption).
6. Empty states that teach instead of showing a blank panel.
7. Status/observability rendered as a calm dashboard, not raw logs.

---

## 2. Recommended visual direction

- **Mood:** premium developer tool. Confident, calm, high-contrast. Soft
  gradients anchored on a deep, saturated base — never pale or washed out.
- **Base surfaces:** deepen the dark base (toward near-navy/black) so the teal→
  indigo→violet gradient pops. Light mode gets crisp white cards on a soft cool
  grey canvas with real borders and shadow separation. Comfort mode is warm
  paper with larger type and high-contrast warm ink.
- **Identity accent:** teal (`brand`) primary, indigo (`brand2`) secondary,
  violet (`accent`) for graph/trace, pink (`accent2`) sparingly.
- **Depth:** 1px theme-aware borders + soft shadow tokens. Reserve glass for the
  marketing hero only; product surfaces use solid panels for readability.
- **Motion:** subtle. Fade-up on reveal, gentle hover lift, status pulse,
  voice-level bars. No gratuitous animation.

---

## 3. Design tokens to introduce

Implemented as CSS variables in `app/globals.css` (`:root` + `[data-theme]`)
and surfaced through `tailwind.config.ts`. All component styling consumes these
tokens — **no hardcoded hex in components**.

### Color / surface
| Token | Purpose |
|---|---|
| `--c-ink` | base background |
| `--c-ink-2` | secondary background band (sections) |
| `--c-panel` | raised card surface |
| `--c-panel-2` | nested/inset surface |
| `--c-edge` | default hairline border |
| `--c-edge-strong` | emphasized border (focus/active cards) |
| `--c-text` | primary text |
| `--c-text-2` | secondary text (≥4.5:1) |
| `--c-text-3` | tertiary/caption text (≥4.5:1 on panel) |
| `--brand-fg` | brand accent adjusted per theme for contrast |

### Semantic status
| Token | Use |
|---|---|
| `--ok` / `--ok-fg` | healthy / strong evidence |
| `--warn` / `--warn-fg` | degraded / weak evidence / abstention |
| `--bad` / `--bad-fg` | offline / failed |
| `--info` | neutral informational |

### Elevation / radius / focus
- `--shadow-sm`, `--shadow-md`, `--shadow-lg` (low-spread, theme-aware).
- `--radius` scale via Tailwind (`rounded-xl`/`2xl`).
- `--ring` focus-ring color; a shared `.focusable` utility for visible focus.

### Typography scale
- Display (hero), `h1`/`h2`/`h3`, body, `caption`, `overline`. Tightened
  tracking on headings; relaxed leading on body. Comfort mode bumps base size.

### Component classes (consolidated, reused everywhere)
`.card`, `.card-inset`, `.btn-cta`, `.btn-outline`, `.btn-brand`, `.btn-ghost`,
`.chip`, `.pill` (+ `.pill-ok/warn/bad`), `.tab`/`.tab-active`, `.stat`,
`.evidence-card`, `.section-title`, `.overline`, `.focusable`.

---

## 4. Layout improvements

**Landing**
- Deeper hero base + richer gradient; product mockup with more confidence.
- One-line explainer under the headline.
- Trust badges row: Local-first · $0 default · Open source · Citations on every
  answer · Voice in/out · Provider-agnostic.
- System status promoted to grouped premium status cards (API, Corpus, Vector
  DB, Embeddings, LLM, ASR/TTS, Tracing) with clear healthy/degraded/offline.
- "How it works" becomes a left-to-right pipeline:
  Upload → Parse → Chunk → Index → Retrieve → Rerank → Reason → Cite → Observe.
- New "What makes Auralynq different?" proof section.
- Stronger final CTA with "Launch Auralynq" + "Read docs" + Podman/dev note.

**Chat**
- Fixed top app bar: logo · live status · theme · settings/new chat.
- Two-pane workspace: wide conversation + contextual inspector.
- Conversation column widened; better message spacing/readability.
- Sticky composer with mode selector + mic + upload.
- Inspector **never empty**: when no query is selected it shows corpus summary,
  system status, recent trace summary, suggested questions, and an upload CTA.

---

## 5. Component improvements

- **Cards:** solid panel surface, hairline border, soft shadow, hover lift,
  strong heading contrast. Kill the washed-out glass on product surfaces.
- **Status pills:** semantic color tokens, dot + label, readable at small size.
- **Citation cards:** title (cleaned, no raw paths), page/section, relevance
  score, snippet, "why selected". Raw chunk IDs/paths behind a debug disclosure.
- **Trace cards:** per-step status icon, duration bar, provider, evidence count,
  warnings. Summary stat grid on top.
- **Evidence cards:** strength-tiered visual treatment (strong/weak/insufficient
  /unsupported).
- **Empty states:** every panel has a purposeful, instructive empty state.
- **Voice:** promoted from a small button to a central, polished control with
  explicit states (idle/listening/transcribing/thinking/speaking/failed).

---

## 6. Accessibility / contrast problems in the current UI

| Problem | Fix |
|---|---|
| Light mode too pale; cards blend into the canvas | Deeper canvas band + real card borders + shadow; darker secondary text token |
| Capability/`glass` cards use `text-slate-300` on translucent white → low contrast, esp. light/comfort | Replace with token-based text (`--c-text-2`) on solid panels |
| `.chip` uses `text-slate-200` on `bg-white/[0.07]` → weak in light mode | Token-based chip with theme-aware border/bg/text |
| Tiny status strip text (`text-[10px]`) hard to read | Larger status cards, ≥12px labels |
| Focus styles rely on default outline / `focus:border-brand` only | Shared visible `.focusable` ring on all interactive elements |
| Raw internal paths shown to users (info + clutter) | `displaySource()` cleans paths; raw behind debug |
| Brand-colored text on light surfaces could fail contrast | `--brand-fg` darkened per theme (already partly done; extend) |

Target: body and secondary text ≥ 4.5:1; large text ≥ 3:1 in all three themes.

---

## 7. Mobile / responsive risks

- Chat two-pane grid collapses to a single column on small screens; the
  inspector must become a bottom drawer / toggle, not a hidden panel.
- Composer must stay reachable (sticky) and the mic must remain tappable.
- Landing capability grid: 3→2→1 columns; status cards 7→4→2.
- Pipeline ("how it works") switches from horizontal to vertical on mobile.
- Long citation sources/paths must truncate, not overflow.
- Hero mockup must scale/center and not force horizontal scroll.

---

## 8. Phased implementation checklist

**Phase 0 — Audit (this doc).** ✅

**Phase 1 — Design tokens & theme.**
- [ ] Deepen dark base; crisp light; warm comfort; all ≥4.5:1 secondary text.
- [ ] Add semantic status + elevation + text-scale tokens.
- [ ] Consolidate `.card/.chip/.pill/.btn-*/.tab/.stat/.evidence-card`.
- [ ] Shared `.focusable` ring; no-flash theme boot (keep).

**Phase 2 — Landing.**
- [ ] Hero: deeper gradient, explainer line, dual CTAs, trust badges, mockup.
- [ ] System status: grouped premium cards w/ healthy/degraded/offline.
- [ ] Capabilities: 6 distinct, high-contrast benefit cards.
- [ ] How it works: 9-step pipeline (responsive).
- [ ] Differentiators proof section.
- [ ] Final CTA + Podman/dev note. Nav/Footer polish.

**Phase 3 — Chat shell.**
- [ ] Fixed app bar; wide conversation; sticky composer.
- [ ] Mode selector + mic states + upload in composer.
- [ ] Never-empty inspector (corpus/status/trace/suggestions/upload).
- [ ] Responsive inspector drawer.

**Phase 4 — Inspector panels.**
- [ ] Evidence: coverage, source breakdown, clean citation cards, debug
      disclosure, strength tiers, empty state.
- [ ] Trace: summary dashboard, timeline steps, Phoenix card + degraded hint.
- [ ] Ingest: drag-drop, types, stats, recent, samples, reindex/clear.
- [ ] Eval: useful placeholder + planned evals + manual feedback widget.
- [ ] Corpus inventory rendering (count/types/languages/topics/last-indexed).
- [ ] Insufficient-evidence: cleaner, softer warning styling.

**Phase 5 — Citations cleanup.**
- [ ] `displaySource()` strips `/app/data/storage/uploads/...` → filename.
- [ ] Raw path/chunk-id only behind debug disclosure.

**Phase 6 — Themes & responsive QA.**
- [ ] Light/dark/comfort polish; persisted + no flash.
- [ ] Laptop/desktop/tablet/mobile pass.

**Phase 7 — Tests & gates.**
- [ ] Unit tests: citation cleaning, theme, panel/render helpers.
- [ ] typecheck · lint · build · container web build · live smoke.

**Phase 8 — Deploy verification.**
- [ ] Rebuild web image, restart stack, verify live, no stale bundle.
- [ ] In-corpus / out-of-corpus / inventory questions; all four panels.
</content>
</invoke>
