// Auralynq API client. Talks to the FastAPI backend.
import { consumeSSE, parseSSEFrame } from "@/lib/sse";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export interface Citation {
  marker: number;
  source: string;
  locator: string;
  source_type: string;
  speaker?: string | null;
  start_s?: number | null;
  end_s?: number | null;
  page?: number | null;
  score?: number | null;   // retrieval score (0-1) — evidence quality
  method?: string | null;  // retrieval method: "hybrid" | "pathrag" | …
}

export interface PathEvidence {
  nodes: string[];
  relations: string[];
  reliability: number;
  ppr_score?: number;  // Personalised PageRank terminal-node authority (0-1)
  text: string;
  chunk_ids: string[];
}

export interface TraceSpan {
  name: string;
  duration_ms: number;
  attributes: Record<string, unknown>;
  events: unknown[];
}

export interface TraceStep {
  id: number;
  name: string;
  label: string;
  status: "success" | "warning" | "failed" | "skipped" | "running" | "pending";
  duration_ms: number;
  provider?: string | null;
  evidence_count?: number | null;
  warnings: string[];
  attributes: Record<string, unknown>;
}

export interface InsufficientReason {
  summary: string;
  detected_entities: string[];
  route_attempted: string;
  retrieved_snippets: { source: string; locator: string; score: number; text: string }[];
  why_insufficient: string;
  suggested_questions: string[];
  suggest_ingest: boolean;
}

export interface AnswerResult {
  answer: string;
  status?: string;
  citations: Citation[];
  route: string;
  route_confidence: number;
  route_rationale: string;
  path_evidence: PathEvidence[];
  seeds: string[];
  iterations: number;
  confidence: number;
  evidence_coverage?: number;
  cached: boolean;
  elapsed_ms: number;
  trace: TraceSpan[];
  trace_steps?: TraceStep[];
  detected_entities?: string[];
  suggested_questions?: string[];
  insufficient_evidence_reason?: InsufficientReason | null;
  warnings?: string[];
  provider_status?: { subsystem: string; provider: string }[];
  visual_grounding?: VisualGrounding | null;
  selected_rag_strategy?: string | null;
  fallback_strategy?: string | null;
  strategy_warnings?: string[];
}

export interface CorpusSummary {
  indexed: boolean;
  indexed_document_count: number;
  vector_count: number;
  document_titles: string[];
  source_types: Record<string, number>;
  top_entities: { name: string; type: string; mentions: number; chunks: number }[];
  entity_count: number;
  last_indexed: string | null;
  last_document_title?: string | null;
  languages?: string[];
  failed_files?: string[];
}

export type StreamEvent =
  | {
      type: "meta";
      route: string;
      confidence: number;
      rationale: string;
      seeds: string[];
      path_evidence: PathEvidence[];
      detected_entities?: string[];
      evidence_coverage?: number;
      rag_strategy?: string;
    }
  | { type: "token"; text: string }
  | {
      type: "final";
      answer: string;
      status?: string;
      citations: Citation[];
      confidence: number;
      evidence_coverage?: number;
      elapsed_ms: number;
      trace: TraceSpan[];
      trace_steps?: TraceStep[];
      detected_entities?: string[];
      suggested_questions?: string[];
      insufficient_evidence_reason?: InsufficientReason | null;
      warnings?: string[];
      selected_rag_strategy?: string;
      fallback_strategy?: string | null;
      fallback_reason?: string | null;
      strategy_warnings?: string[];
      visual_grounding?: VisualGrounding | null;
    };

export interface RAGStrategyInfo {
  id: string;
  name: string;
  description: string;
  status: "available" | "experimental" | "planned";
  required_features: string[];
  supports_streaming: boolean;
  supports_graph: boolean;
  supports_rerank: boolean;
  supports_web: boolean;
  supports_abstention: boolean;
  expected_latency: "fast" | "medium" | "slow";
  best_for: string;
  limitations: string;
  available: boolean;
  unavailable_reason: string | null;
}

export interface EvalMetrics {
  strategy?: string;
  route?: string;
  confidence?: number;
  evidence_coverage?: number;
  citations?: number;
  elapsed_ms?: number;
  status?: string;
  warnings?: string[];
}

export async function health() {
  const r = await fetch(`${API_BASE}/health`, { cache: "no-store" });
  return r.json();
}

export async function corpusSummary(): Promise<CorpusSummary> {
  const r = await fetch(`${API_BASE}/corpus/summary`, { cache: "no-store" });
  if (!r.ok) throw new Error(`corpus summary failed: ${r.status}`);
  return r.json();
}

export async function fetchSuggestions(
  limit = 4,
): Promise<{ suggestions: string[]; corpus_indexed: boolean }> {
  const r = await fetch(`${API_BASE}/suggestions?limit=${limit}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`suggestions failed: ${r.status}`);
  return r.json();
}

export async function statusSummary() {
  const r = await fetch(`${API_BASE}/status`, { cache: "no-store" });
  if (!r.ok) throw new Error(`status failed: ${r.status}`);
  return r.json();
}

export async function observabilitySummary() {
  const r = await fetch(`${API_BASE}/observability/summary`, { cache: "no-store" });
  if (!r.ok) throw new Error(`observability failed: ${r.status}`);
  return r.json();
}

export async function ask(question: string, finalK?: number): Promise<AnswerResult> {
  const r = await fetch(`${API_BASE}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, final_k: finalK }),
  });
  if (!r.ok) throw new Error(`query failed: ${r.status}`);
  return r.json();
}

// Stream tokens via SSE-over-POST using the fetch streaming body.
export async function askStream(
  question: string,
  onEvent: (e: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const r = await fetch(`${API_BASE}/query/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
    signal,
  });
  if (!r.ok) {
    const detail = await r.text().catch(() => "");
    throw new Error(`stream failed: ${r.status} ${detail.slice(0, 200)}`);
  }
  if (!r.body) throw new Error("no stream body");
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const { events, rest } = consumeSSE<StreamEvent>(buf);
    buf = rest;
    for (const ev of events) onEvent(ev);
  }
  // Flush any final buffered frame (stream may end without a trailing blank line).
  if (buf.trim()) {
    const ev = parseSSEFrame<StreamEvent>(buf);
    if (ev) onEvent(ev);
  }
}

export async function ingestFile(file: File) {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`${API_BASE}/ingest`, { method: "POST", body: fd });
  if (!r.ok) throw new Error(`ingest failed: ${r.status}`);
  return r.json();
}

export async function sendVoice(blob: Blob) {
  const fd = new FormData();
  fd.append("file", new File([blob], "speech.webm", { type: blob.type }));
  const r = await fetch(`${API_BASE}/voice`, { method: "POST", body: fd });
  if (!r.ok) throw new Error(`voice failed: ${r.status}`);
  return r.json();
}

export async function evalReport() {
  const r = await fetch(`${API_BASE}/eval/report`, { cache: "no-store" });
  return r.json();
}

export function audioUrl() {
  return `${API_BASE}/voice/audio?t=${Date.now()}`;
}

// --- Corpus management ---------------------------------------------------

export interface DocumentMeta {
  doc_id: string;
  source: string;
  title: string;
  source_type: string;
  chunks?: number;
  vectors?: number;
  ingested_at?: string | null;
}

export interface CorpusClearPreview {
  action: string;
  document_count: number;
  vector_count: number;
  entity_count: number;
  files: string[];
  document_details: DocumentMeta[];
  manifest_entries: number;
  graph_exists: boolean;
  confirmation_phrase: string;
  warning: string;
}

export interface CorpusDeleteDocumentPreview {
  action: string;
  found: boolean;
  document: DocumentMeta | null;
  confirmation_phrase: string;
  warning?: string;
}

export interface CorpusDeleteReport {
  action: string;
  deleted: boolean;
  deleted_vectors: number;
  deleted_documents: number;
  deleted_entities: number;
  deleted_chunks: number;
  errors: string[];
  reason?: string | null;
}

export async function corpusClearPreview(): Promise<CorpusClearPreview> {
  const r = await fetch(`${API_BASE}/corpus/clear/preview`, { method: "POST", cache: "no-store" });
  if (!r.ok) throw new Error(`corpus clear preview failed: ${r.status}`);
  return r.json();
}

export async function corpusClearConfirm(phrase: string): Promise<CorpusDeleteReport> {
  const r = await fetch(`${API_BASE}/corpus/clear/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phrase }),
  });
  if (!r.ok) {
    const detail = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(detail.detail || `confirm failed: ${r.status}`);
  }
  return r.json();
}

export async function corpusDeleteLastPreview(): Promise<CorpusDeleteDocumentPreview> {
  const r = await fetch(`${API_BASE}/corpus/documents/last/preview`, { cache: "no-store" });
  if (!r.ok) throw new Error(`delete last preview failed: ${r.status}`);
  return r.json();
}

export async function corpusDeleteLastConfirm(phrase: string): Promise<CorpusDeleteReport> {
  const r = await fetch(`${API_BASE}/corpus/documents/last/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phrase }),
  });
  if (!r.ok) {
    const detail = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(detail.detail || `confirm failed: ${r.status}`);
  }
  return r.json();
}

export async function corpusDeleteDocumentPreview(docId: string): Promise<CorpusDeleteDocumentPreview> {
  const r = await fetch(`${API_BASE}/corpus/documents/${encodeURIComponent(docId)}/preview`, { cache: "no-store" });
  if (!r.ok) throw new Error(`delete document preview failed: ${r.status}`);
  return r.json();
}

export async function corpusDeleteDocumentConfirm(docId: string, phrase: string): Promise<CorpusDeleteReport> {
  const r = await fetch(`${API_BASE}/corpus/documents/${encodeURIComponent(docId)}/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phrase }),
  });
  if (!r.ok) {
    const detail = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(detail.detail || `confirm failed: ${r.status}`);
  }
  return r.json();
}

// --- RAG strategies -------------------------------------------------------

export async function fetchRAGStrategies(): Promise<{ strategies: RAGStrategyInfo[]; default_strategy: string }> {
  const r = await fetch(`${API_BASE}/rag/strategies`, { cache: "no-store" });
  if (!r.ok) throw new Error(`strategies failed: ${r.status}`);
  return r.json();
}

// --- Eval -----------------------------------------------------------------

export async function evalLast(): Promise<EvalMetrics | null> {
  const r = await fetch(`${API_BASE}/eval/last`, { cache: "no-store" });
  if (!r.ok) return null;
  const data = await r.json();
  if (data.status === "pending") return null;
  return data as EvalMetrics;
}

export async function postEvalFeedback(payload: {
  answer_rating?: number;
  citation_correct?: boolean;
  answer_supported?: boolean;
  notes?: string;
}) {
  const r = await fetch(`${API_BASE}/eval/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(`feedback failed: ${r.status}`);
  return r.json();
}

export async function exportEvalRun() {
  const r = await fetch(`${API_BASE}/eval/export-run`, { method: "POST", cache: "no-store" });
  if (!r.ok) throw new Error(`export failed: ${r.status}`);
  return r.json();
}

export async function runEval(): Promise<any> {
  const r = await fetch(`${API_BASE}/eval/run`, { method: "POST", cache: "no-store" });
  if (!r.ok) throw new Error(`eval run failed: ${r.status}`);
  return r.json();
}

// --- Visual grounding -------------------------------------------------------

export interface VisualHighlight {
  citation_id: string;
  chunk_id: string;
  doc_id: string;
  source_title: string;
  page: number | null;
  page_image_url: string;
  bbox: [number, number, number, number] | null;
  normalized_bbox: [number, number, number, number] | null;
  color_index: number;
  snippet: string;
  support_type: "span" | "page" | "unavailable" | "graph";
  relevance: number;
  confidence: number;
  block_type: string;
  grounding_version: number;
  reindex_required: boolean;
}

export interface ClaimGrounding {
  claim_id: string;
  text: string;
  citation_ids: string[];
  support_status: "supported" | "partial" | "weak" | "unsupported";
  visual_evidence_ids: string[];
  confidence: number;
}

export interface VisualGrounding {
  highlights: VisualHighlight[];
  claim_grounding: ClaimGrounding[];
  warnings: string[];
  visual_grounding_available: boolean;
  grounding_stage: "span" | "page" | "unavailable";
}

export interface PageInfo {
  page: number;
  width: number;
  height: number;
  image_url: string;
  has_image: boolean;
}

export interface DocumentPagesResponse {
  doc_id: string;
  source_title: string;
  source_type: string;
  n_pages: number;
  pages: PageInfo[];
  visual_grounding_version: number;
  reindex_required: boolean;
}

export async function fetchDocumentPages(docId: string): Promise<DocumentPagesResponse> {
  const r = await fetch(`${API_BASE}/documents/${encodeURIComponent(docId)}/pages`, { cache: "no-store" });
  if (!r.ok) throw new Error(`document pages failed: ${r.status}`);
  return r.json();
}

export function documentPageImageUrl(docId: string, page: number): string {
  return `${API_BASE}/documents/${encodeURIComponent(docId)}/pages/${page}/image`;
}

export async function fetchGroundingStatus(docId: string) {
  const r = await fetch(`${API_BASE}/documents/${encodeURIComponent(docId)}/grounding-status`, { cache: "no-store" });
  if (!r.ok) throw new Error(`grounding status failed: ${r.status}`);
  return r.json();
}

export interface GroundingSummary {
  enabled: boolean;
  page_rendering_enabled: boolean;
  total_docs: number;
  grounded_docs: number;
  needs_reindex: number;
  visual_grounding_version: number;
}

export async function fetchGroundingSummary(): Promise<GroundingSummary> {
  const r = await fetch(`${API_BASE}/corpus/grounding-summary`, { cache: "no-store" });
  if (!r.ok) throw new Error(`grounding summary failed: ${r.status}`);
  return r.json();
}

export interface PageLayoutBlock {
  block_id: string;
  page: number;
  bbox: number[];
  normalized_bbox: number[];
  text: string;
  block_type: string;
  chunk_id: string;
  relevance: number;
  confidence: number;
  is_cited: boolean;
  citation_ids: string[];
}

export interface PageLayoutResponse {
  doc_id: string;
  page: number;
  blocks: PageLayoutBlock[];
  source_title: string;
  page_width: number;
  page_height: number;
}

export async function fetchPageLayout(docId: string, page: number): Promise<PageLayoutResponse> {
  const r = await fetch(`${API_BASE}/documents/${encodeURIComponent(docId)}/pages/${page}/layout`, { cache: "no-store" });
  if (!r.ok) throw new Error(`page layout failed: ${r.status}`);
  return r.json();
}

// Stream with strategy selection
export async function askStreamWithStrategy(
  question: string,
  strategyId: string | null,
  onEvent: (e: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const r = await fetch(`${API_BASE}/query/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, rag_strategy: strategyId }),
    signal,
  });
  if (!r.ok) {
    const detail = await r.text().catch(() => "");
    throw new Error(`stream failed: ${r.status} ${detail.slice(0, 200)}`);
  }
  if (!r.body) throw new Error("no stream body");
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const { events, rest } = consumeSSE<StreamEvent>(buf);
    buf = rest;
    for (const ev of events) onEvent(ev);
  }
  if (buf.trim()) {
    const ev = parseSSEFrame<StreamEvent>(buf);
    if (ev) onEvent(ev);
  }
}
