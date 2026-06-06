"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  AnswerResult,
  CorpusSummary,
  PathEvidence,
  StreamEvent,
  TraceSpan,
  TraceStep,
  askStream,
  corpusSummary,
  fetchSuggestions,
  health,
  statusSummary,
} from "@/lib/api";
import { isCorpusManagementQuestion, isInventoryQuestion } from "@/lib/format";
import { Message, type Turn } from "@/components/Message";
import { TracePanel } from "@/components/TracePanel";
import { EvidencePaths } from "@/components/EvidencePaths";
import { IngestPanel } from "@/components/IngestPanel";
import { EvalPanel } from "@/components/EvalPanel";
import { AppBar } from "@/components/chat/AppBar";
import { Composer, type ChatMode } from "@/components/chat/Composer";
import { InspectorOverview, type RecentMeta } from "@/components/chat/InspectorOverview";

const FALLBACK_SUGGESTIONS = [
  "Summarize the main topics in the indexed documents.",
  "What are the key entities and how do they relate?",
];
const STORE_KEY = "auralynq.chat.v1";
const TABS = ["overview", "trace", "evidence", "ingest", "eval"] as const;
type Tab = (typeof TABS)[number];

export default function Chat() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<ChatMode>("corpus");
  const [streaming, setStreaming] = useState(false);
  const [trace, setTrace] = useState<TraceSpan[]>([]);
  const [traceSteps, setTraceSteps] = useState<TraceStep[]>([]);
  const [paths, setPaths] = useState<PathEvidence[]>([]);
  const [seeds, setSeeds] = useState<string[]>([]);
  const [coverage, setCoverage] = useState(0);
  const [lastConfidence, setLastConfidence] = useState(0);
  const [lastRoute, setLastRoute] = useState("fast");
  const [lastStatus, setLastStatus] = useState<string>("answered");
  const [tab, setTab] = useState<Tab>("overview");
  const [showPanel, setShowPanel] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>(FALLBACK_SUGGESTIONS);
  const [phoenixUrl, setPhoenixUrl] = useState<string | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const [vectors, setVectors] = useState<number | null>(null);
  const [hasAnswered, setHasAnswered] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // --- bootstrap: status, suggestions, persisted conversation -------------
  useEffect(() => {
    health()
      .then(() => setOnline(true))
      .catch(() => setOnline(false));
    fetchSuggestions(4)
      .then((s) => {
        if (s.suggestions?.length) setSuggestions(s.suggestions);
      })
      .catch(() => {});
    statusSummary()
      .then((s) => {
        setPhoenixUrl(s?.tracing?.phoenix_endpoint || null);
        setVectors(s?.index?.vectors ?? s?.corpus?.vector_count ?? null);
      })
      .catch(() => {});
    try {
      const raw = localStorage.getItem(STORE_KEY);
      if (raw) {
        const restored: Turn[] = JSON.parse(raw);
        setTurns(restored);
        if (restored.length) setHasAnswered(true);
      }
    } catch {
      /* ignore corrupt cache */
    }
  }, []);

  // Persist after each completed turn (not per token).
  useEffect(() => {
    if (streaming) return;
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(turns.slice(-50)));
    } catch {
      /* quota / private mode — non-fatal */
    }
  }, [turns, streaming]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const flash = useCallback((m: string) => {
    setToast(m);
    setTimeout(() => setToast(null), 2200);
  }, []);

  function patchLast(update: Partial<Turn>) {
    setTurns((t) => {
      const c = [...t];
      c[c.length - 1] = { ...c[c.length - 1], ...update };
      return c;
    });
  }

  const runStream = useCallback(async (q: string) => {
    setStreaming(true);
    setTrace([]);
    setTraceSteps([]);
    setPaths([]);
    setSeeds([]);
    setCoverage(0);
    setLastStatus("answered");
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      await askStream(
        q,
        (e: StreamEvent) => {
          if (e.type === "meta") {
            setPaths(e.path_evidence || []);
            setSeeds(e.seeds || []);
            setCoverage(e.evidence_coverage ?? 0);
            setLastRoute(e.route);
            setTab(e.route === "fast" ? "trace" : "evidence");
            patchLast({ route: e.route, rationale: e.rationale });
          } else if (e.type === "token") {
            setTurns((t) => {
              const c = [...t];
              c[c.length - 1] = { ...c[c.length - 1], text: c[c.length - 1].text + e.text };
              return c;
            });
          } else if (e.type === "final") {
            setTrace(e.trace || []);
            setTraceSteps(e.trace_steps || []);
            setCoverage(e.evidence_coverage ?? 0);
            setLastConfidence(e.confidence ?? 0);
            setLastStatus(e.status || "answered");
            patchLast({
              text: e.answer,
              citations: e.citations,
              status: e.status,
              insufficient: e.insufficient_evidence_reason || null,
              confidence: e.confidence ?? 0,
              semanticCoverage: (e as any).semantic_coverage ?? undefined,
            });
            if (e.status === "insufficient_evidence") setTab("evidence");
          }
        },
        ac.signal,
      );
    } catch (err) {
      if (ac.signal.aborted) {
        setTurns((t) => {
          const c = [...t];
          const last = c[c.length - 1];
          if (last?.role === "assistant" && !last.text)
            c[c.length - 1] = { ...last, text: "⏹ Stopped." };
          return c;
        });
      } else {
        patchLast({ text: `Couldn't reach the backend: ${(err as Error).message}`, error: true });
      }
    } finally {
      setStreaming(false);
      setHasAnswered(true);
      abortRef.current = null;
    }
  }, []);

  // Inventory questions are answered from corpus metadata, not the evidence
  // pipeline — so "what's in my collection?" never reads as a failure.
  const answerInventory = useCallback(async (q: string) => {
    let summary: CorpusSummary | null = null;
    try {
      summary = await corpusSummary();
    } catch {
      /* fall through to a graceful message */
    }
    setTurns((t) => {
      const c = [...t];
      c[c.length - 1] = summary
        ? { role: "assistant", text: "", inventory: summary, question: q }
        : {
            role: "assistant",
            text: "I couldn't read the corpus inventory right now — the backend may be warming up.",
            error: true,
          };
      return c;
    });
    setHasAnswered(true);
    setTab("overview");
  }, []);

  // Shape the outgoing query by composer mode.
  const shapeQuery = useCallback((q: string, m: ChatMode): string => {
    const t = q.trim();
    if (m === "summarize") {
      return t ? `Summarize the key points about: ${t}` : "Summarize the main topics in the indexed documents.";
    }
    return t;
  }, []);

  const send = useCallback(
    (raw: string) => {
      const q = shapeQuery(raw, mode);
      if (!q.trim() || streaming) return;
      setInput("");
      setShowPanel(false);
      const inventory = mode === "inventory" || isInventoryQuestion(q);
      setTurns((t) => [...t, { role: "user", text: q }, { role: "assistant", text: "" }]);
      if (inventory) {
        void answerInventory(q);
      } else {
        void runStream(q);
      }
    },
    [streaming, runStream, answerInventory, mode, shapeQuery],
  );

  const regenerate = useCallback(() => {
    if (streaming) return;
    const lastUser = [...turns].reverse().find((t) => t.role === "user");
    if (!lastUser) return;
    setTurns((t) => {
      const c = [...t];
      if (c.length && c[c.length - 1].role === "assistant") c.pop();
      c.push({ role: "assistant", text: "" });
      return c;
    });
    void runStream(lastUser.text);
  }, [streaming, turns, runStream]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    flash("Generation stopped");
  }, [flash]);

  const newChat = useCallback(() => {
    abortRef.current?.abort();
    setTurns([]);
    setTrace([]);
    setPaths([]);
    setSeeds([]);
    setHasAnswered(false);
    setTab("overview");
    try {
      localStorage.removeItem(STORE_KEY);
    } catch {
      /* ignore */
    }
    flash("New chat");
  }, [flash]);

  // Global shortcuts: Esc stops a stream, Cmd/Ctrl+K starts a new chat.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && streaming) stop();
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        newChat();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [streaming, stop, newChat]);

  function onVoice(r: AnswerResult & { transcript?: string }) {
    setTurns((t) => [
      ...t,
      { role: "user", text: r.transcript || "voice query", voice: true },
      { role: "assistant", text: r.answer, citations: r.citations, route: r.route },
    ]);
    setPaths(r.path_evidence || []);
    setSeeds(r.seeds || []);
    if (r.trace) setTrace(r.trace);
    setHasAnswered(true);
  }

  const openIngest = useCallback(() => {
    setShowPanel(true);
    setTab("ingest");
  }, []);

  // Refresh inventory/suggestions after corpus deletion
  const onCorpusDeleted = useCallback(async () => {
    setPaths([]);
    setSeeds([]);
    try {
      const [s, sug] = await Promise.all([
        statusSummary(),
        fetchSuggestions(4),
      ]);
      setVectors(s?.index?.vectors ?? s?.corpus?.vector_count ?? 0);
      if (sug.suggestions?.length) setSuggestions(sug.suggestions);
    } catch {
      setVectors(0);
    }
    // Clear stale localStorage chat so old corpus-referencing turns don't persist
    try {
      localStorage.removeItem(STORE_KEY);
    } catch {
      /* ignore */
    }
    flash("Corpus updated — inventory refreshed");
  }, [flash]);

  const recentMeta: RecentMeta | null = hasAnswered
    ? { route: lastRoute, status: lastStatus, coverage, confidence: lastConfidence }
    : null;

  const lastAssistant = [...turns].reverse().find((t) => t.role === "assistant");

  return (
    <div className="flex h-[100dvh] flex-col bg-ink text-fg">
      <AppBar
        online={online}
        vectors={vectors}
        onNewChat={newChat}
        onToggleInspector={() => setShowPanel((v) => !v)}
        inspectorOpen={showPanel}
      />

      {/* Full-viewport grid: chat | inspector. Inspector always visible on lg+. */}
      <div className="grid w-full flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[minmax(0,1fr)_clamp(320px,28vw,520px)]">
        {/* Conversation column */}
        <section className="flex min-h-0 flex-col">
          <div
            ref={scrollRef}
            role="log"
            aria-live="polite"
            aria-label="Conversation"
            className="scroll-thin flex-1 overflow-y-auto px-3 py-4 md:px-6 xl:px-8"
          >
            <div className="mx-auto max-w-3xl space-y-4">
              {turns.length === 0 ? (
                <EmptyConversation suggestions={suggestions} onAsk={send} onIngest={openIngest} />
              ) : (
                turns.map((t, i) => (
                  <div key={i} className="msg-in">
                    <Message
                      turn={t}
                      streaming={streaming}
                      isLast={i === turns.length - 1}
                      onRegenerate={t.role === "assistant" ? regenerate : undefined}
                      onAsk={send}
                      onIngest={openIngest}
                    />
                  </div>
                ))
              )}
            </div>
          </div>

          {/* sticky composer */}
          <div className="mx-auto w-full max-w-3xl px-2 pb-2">
            <Composer
              input={input}
              setInput={setInput}
              mode={mode}
              setMode={setMode}
              streaming={streaming}
              onSend={send}
              onStop={stop}
              onVoiceResult={onVoice}
              onUploadClick={openIngest}
            />
          </div>
        </section>

        {/* Inspector — always visible on desktop (lg+), mobile drawer when showPanel */}
        <aside
          className={
            showPanel
              ? "fixed inset-0 z-50 flex flex-col border-l border-edge bg-ink/95 backdrop-blur-sm lg:static lg:min-h-0 lg:bg-panel/60"
              : "hidden min-h-0 flex-col border-l border-edge bg-panel/60 lg:flex"
          }
        >
          <div className="flex items-center gap-1 overflow-x-auto border-b border-edge px-3 py-2">
            {TABS.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                aria-pressed={tab === t}
                className={`tab capitalize ${tab === t ? "tab-active" : ""}`}
              >
                {t}
              </button>
            ))}
            <button
              onClick={() => setShowPanel(false)}
              className="btn-ghost ml-auto px-2 py-1 text-sm lg:hidden"
              aria-label="Close inspector"
            >
              ✕
            </button>
          </div>
          <div className="scroll-thin min-h-0 flex-1 overflow-y-auto p-3">
            {tab === "overview" && (
              <InspectorOverview
                suggestions={suggestions}
                recent={recentMeta}
                onAsk={send}
                onIngest={openIngest}
              />
            )}
            {tab === "trace" && (
              <TracePanel
                trace={trace}
                steps={traceSteps}
                meta={{
                  route: lastRoute,
                  status: lastStatus,
                  confidence: lastConfidence,
                  coverage,
                  phoenixUrl,
                }}
              />
            )}
            {tab === "evidence" && (
              <EvidencePaths
                paths={paths}
                seeds={seeds}
                coverage={coverage}
                citations={lastAssistant?.citations || []}
              />
            )}
            {tab === "ingest" && <IngestPanel onAsk={send} onDeleted={onCorpusDeleted} />}
            {tab === "eval" && <EvalPanel />}
          </div>
        </aside>
      </div>

      {toast && (
        <div
          role="status"
          className="fixed bottom-24 left-1/2 z-50 -translate-x-1/2 rounded-xl border border-edge bg-panel px-4 py-2 text-sm shadow-lg"
        >
          {toast}
        </div>
      )}
    </div>
  );
}

function EmptyConversation({
  suggestions,
  onAsk,
  onIngest,
}: {
  suggestions: string[];
  onAsk: (q: string) => void;
  onIngest: () => void;
}) {
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-6 text-center">
      <div className="space-y-2">
        <div className="text-4xl" aria-hidden>
          🎙️
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-fg">Talk to your data</h1>
        <p className="mx-auto max-w-md text-fg2">
          Grounded, cited answers from your indexed documents — by text or voice. Ask a question or
          pick a suggestion to begin.
        </p>
      </div>
      <div className="flex w-full max-w-xl flex-col gap-2">
        {suggestions.slice(0, 4).map((s) => (
          <button
            key={s}
            onClick={() => onAsk(s)}
            className="card card-hover px-4 py-3 text-left text-sm text-fg2"
          >
            <span className="mr-2 text-brand" aria-hidden>
              ↳
            </span>
            {s}
          </button>
        ))}
      </div>
      <button onClick={onIngest} className="btn-ghost text-sm">
        <span aria-hidden>＋</span> Add documents to your corpus
      </button>
    </div>
  );
}
