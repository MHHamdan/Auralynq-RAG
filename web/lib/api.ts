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
}

export interface PathEvidence {
  nodes: string[];
  relations: string[];
  reliability: number;
  text: string;
  chunk_ids: string[];
}

export interface TraceSpan {
  name: string;
  duration_ms: number;
  attributes: Record<string, unknown>;
  events: unknown[];
}

export interface AnswerResult {
  answer: string;
  citations: Citation[];
  route: string;
  route_confidence: number;
  route_rationale: string;
  path_evidence: PathEvidence[];
  seeds: string[];
  iterations: number;
  confidence: number;
  cached: boolean;
  elapsed_ms: number;
  trace: TraceSpan[];
}

export type StreamEvent =
  | { type: "meta"; route: string; confidence: number; rationale: string; seeds: string[]; path_evidence: PathEvidence[] }
  | { type: "token"; text: string }
  | { type: "final"; answer: string; citations: Citation[]; confidence: number; elapsed_ms: number; trace: TraceSpan[] };

export async function health() {
  const r = await fetch(`${API_BASE}/health`, { cache: "no-store" });
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
