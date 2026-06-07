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
  corpusClearPreview,
  corpusClearConfirm,
} from "@/lib/api";
import { isInventoryQuestion } from "@/lib/format";
import { Message, type Turn } from "@/components/Message";
import { TracePanel } from "@/components/TracePanel";
import { EvidencePaths } from "@/components/EvidencePaths";
import { IngestPanel } from "@/components/IngestPanel";
import { EvalPanel } from "@/components/EvalPanel";
import { AppBar } from "@/components/chat/AppBar";
import { Composer, type ChatMode } from "@/components/chat/Composer";
import { InspectorOverview, type RecentMeta } from "@/components/chat/InspectorOverview";
import { AgentActivityRail, type AgentActivity } from "@/components/chat/AgentActivityRail";
import { SettingsPanel, useUISettings } from "@/components/chat/SettingsPanel";
import { loadStoredStrategy } from "@/components/chat/AlgorithmSelector";

const FALLBACK_SUGGESTIONS = [
  "Summarize the main topics in the indexed documents.",
  "What are the key entities and how do they relate?",
];
const STORE_KEY = "auralynq.chat.v1";
const TABS = ["overview", "trace", "evidence", "ingest", "eval"] as const;
type Tab = (typeof TABS)[number];

function computeRisk(confidence: number, coverage: number): AgentActivity["riskLevel"] {
  if (confidence >= 0.8 && coverage >= 0.8) return "none";
  if (confidence >= 0.6 && coverage >= 0.6) return "low";
  if (confidence >= 0.4) return "medium";
  return "high";
}

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
  const [entities, setEntities] = useState<number | null>(null);
  const [hasAnswered, setHasAnswered] = useState(false);
  const [corpusRefreshKey, setCorpusRefreshKey] = useState(0);
  const [ragStrategy, setRagStrategy] = useState<string>("auralynq_rag");
  const [showSettings, setShowSettings] = useState(false);
  const [agentActivity, setAgentActivity] = useState<AgentActivity>({ phase: "idle" });
  // new-chat corpus-clear confirmation state
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false);
  const [clearLoading, setClearLoading] = useState(false);
  const [clearError, setClearError] = useState<string | null>(null);

  const { settings, update: updateSettings } = useUISettings();

  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Load persisted RAG strategy
  useEffect(() => {
    setRagStrategy(loadStoredStrategy());
  }, []);

  // Bootstrap: status, suggestions, persisted conversation
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
        const vecs = s?.index?.vectors ?? s?.corpus?.vector_count ?? null;
        const ents = s?.corpus?.entity_count ?? null;
        setVectors(vecs);
        setEntities(ents);
        if (vecs === 0) {
          try { localStorage.removeItem(STORE_KEY); } catch { /* ignore */ }
          setAgentActivity({ phase: "corpus_empty" });
          return;
        }
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
      })
      .catch(() => {
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
      });
  }, []);

  // Persist after each completed turn
  useEffect(() => {
    if (streaming) return;
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(turns.slice(-50)));
    } catch {
      /* quota / private mode */
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
    setAgentActivity({ phase: "query_received", algorithm: ragStrategy });
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
            const isSystemRoute = ["corpus_inventory", "corpus_management", "app_help"].includes(e.route);
            setAgentActivity({
              phase: isSystemRoute ? "system_route" : "retrieval_started",
              route: e.route,
              algorithm: (e as any).rag_strategy || ragStrategy,
              coverage: e.evidence_coverage ?? 0,
            });
            setTab(e.route === "fast" ? "overview" : "evidence");
            patchLast({ route: e.route, rationale: e.rationale });
          } else if (e.type === "token") {
            setAgentActivity((prev) => ({ ...prev, phase: "generating" }));
            setTurns((t) => {
              const c = [...t];
              c[c.length - 1] = { ...c[c.length - 1], text: c[c.length - 1].text + e.text };
              return c;
            });
          } else if (e.type === "final") {
            setTrace(e.trace || []);
            setTraceSteps(e.trace_steps || []);
            const finalCov = e.evidence_coverage ?? 0;
            const finalConf = e.confidence ?? 0;
            setCoverage(finalCov);
            setLastConfidence(finalConf);
            setLastStatus(e.status || "answered");
            const risk = computeRisk(finalConf, finalCov);
            setAgentActivity({
              phase: e.status === "insufficient_evidence" ? "abstained" : "done",
              route: lastRoute,
              algorithm: (e as any).selected_rag_strategy || ragStrategy,
              coverage: finalCov,
              confidence: finalConf,
              riskLevel: risk,
              latencyMs: e.elapsed_ms,
              warnings: e.warnings,
              fallback: (e as any).fallback_strategy || null,
            });
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
        setAgentActivity({ phase: "idle" });
      } else {
        patchLast({ text: `Couldn't reach the backend: ${(err as Error).message}`, error: true });
        setAgentActivity({ phase: "error", error: (err as Error).message });
      }
    } finally {
      setStreaming(false);
      setHasAnswered(true);
      abortRef.current = null;
    }
  }, [ragStrategy, lastRoute]);

  const answerInventory = useCallback(async (q: string) => {
    setAgentActivity({ phase: "system_route", route: "corpus_inventory" });
    let summary: CorpusSummary | null = null;
    try {
      summary = await corpusSummary();
    } catch {
      /* fall through */
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
    setAgentActivity({ phase: "done", route: "corpus_inventory" });
  }, []);

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

  const handleNewChat = useCallback(() => {
    const m = settings.newChatMode;
    if (m === "chat_only") {
      abortRef.current?.abort();
      setTurns([]);
      setTrace([]);
      setPaths([]);
      setSeeds([]);
      setHasAnswered(false);
      setTab("overview");
      setAgentActivity({ phase: "idle" });
      try { localStorage.removeItem(STORE_KEY); } catch { /* ignore */ }
      flash("New chat");
    } else if (m === "new_workspace") {
      abortRef.current?.abort();
      setTurns([]);
      setTrace([]);
      setPaths([]);
      setSeeds([]);
      setHasAnswered(false);
      setTab("ingest");
      setShowPanel(true);
      setAgentActivity({ phase: "idle" });
      try { localStorage.removeItem(STORE_KEY); } catch { /* ignore */ }
      flash("New workspace — manage your corpus in the Ingest panel");
    } else {
      // clear_corpus — open confirmation dialog
      setClearConfirmOpen(true);
      setClearError(null);
    }
  }, [settings.newChatMode, flash]);

  const executeClearCorpus = useCallback(async () => {
    setClearLoading(true);
    setClearError(null);
    try {
      const preview = await corpusClearPreview();
      await corpusClearConfirm(preview.confirmation_phrase);
      // Clear all local state
      abortRef.current?.abort();
      setTurns([]);
      setTrace([]);
      setPaths([]);
      setSeeds([]);
      setHasAnswered(false);
      setTab("overview");
      setAgentActivity({ phase: "corpus_empty" });
      try { localStorage.removeItem(STORE_KEY); } catch { /* ignore */ }
      // Refresh inventory
      const [s, sug] = await Promise.all([statusSummary(), fetchSuggestions(4)]);
      setVectors(s?.index?.vectors ?? s?.corpus?.vector_count ?? 0);
      setEntities(s?.corpus?.entity_count ?? 0);
      if (sug.suggestions?.length) setSuggestions(sug.suggestions);
      setCorpusRefreshKey((k) => k + 1);
      setClearConfirmOpen(false);
      flash("Corpus cleared — fresh workspace ready");
    } catch (err) {
      setClearError((err as Error).message || "Clear failed");
    } finally {
      setClearLoading(false);
    }
  }, [flash]);

  // Global shortcuts: Esc stops, Cmd+K new chat
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && streaming) stop();
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        handleNewChat();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [streaming, stop, handleNewChat]);

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

  const onCorpusDeleted = useCallback(async () => {
    setPaths([]);
    setSeeds([]);
    try {
      const [s, sug] = await Promise.all([statusSummary(), fetchSuggestions(4)]);
      const vecs = s?.index?.vectors ?? s?.corpus?.vector_count ?? 0;
      setVectors(vecs);
      setEntities(s?.corpus?.entity_count ?? 0);
      if (sug.suggestions?.length) setSuggestions(sug.suggestions);
      if (vecs === 0) setAgentActivity({ phase: "corpus_empty" });
    } catch {
      setVectors(0);
    }
    try { localStorage.removeItem(STORE_KEY); } catch { /* ignore */ }
    setCorpusRefreshKey((k) => k + 1);
    flash("Corpus updated — inventory refreshed");
  }, [flash]);

  const recentMeta: RecentMeta | null = hasAnswered
    ? { route: lastRoute, status: lastStatus, coverage, confidence: lastConfidence }
    : null;

  const lastAssistant = [...turns].reverse().find((t) => t.role === "assistant");

  const traceAlwaysVisible = settings.traceVisibility === "always" || settings.traceVisibility === "auto";

  return (
    <div className="flex h-[100dvh] flex-col bg-ink text-fg">
      <AppBar
        online={online}
        vectors={vectors}
        entities={entities}
        onNewChat={handleNewChat}
        onToggleInspector={() => setShowPanel((v) => !v)}
        inspectorOpen={showPanel}
        onToggleSettings={() => setShowSettings((v) => !v)}
      />

      {/* Settings overlay */}
      {showSettings && (
        <div className="fixed inset-0 z-50 flex items-start justify-end">
          <div
            className="fixed inset-0 bg-ink/60 backdrop-blur-sm"
            onClick={() => setShowSettings(false)}
          />
          <div className="relative z-10 mt-14 mr-3 w-80 rounded-xl border border-edge bg-panel shadow-lg">
            <div className="scroll-thin max-h-[80vh] overflow-y-auto p-3">
              <SettingsPanel
                settings={settings}
                onChange={updateSettings}
                onClose={() => setShowSettings(false)}
              />
            </div>
          </div>
        </div>
      )}

      {/* Clear corpus confirmation dialog */}
      {clearConfirmOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="fixed inset-0 bg-ink/70 backdrop-blur-sm"
            onClick={() => !clearLoading && setClearConfirmOpen(false)}
          />
          <div className="relative z-10 w-full max-w-md rounded-2xl border border-edge bg-panel p-6 shadow-xl">
            <h2 className="mb-2 text-base font-bold text-fg">Clear corpus and start fresh?</h2>
            <p className="mb-4 text-sm text-fg2">
              This will remove all indexed documents, vectors, and entities. Your chat history will also be cleared.
              This action cannot be undone.
            </p>
            {clearError && (
              <p className="mb-3 rounded border border-bad/30 bg-bad/10 p-2 text-sm text-bad">{clearError}</p>
            )}
            <div className="flex gap-2">
              <button
                className="btn-ghost flex-1"
                onClick={() => setClearConfirmOpen(false)}
                disabled={clearLoading}
              >
                Cancel
              </button>
              <button
                className="flex-1 rounded-xl border border-bad/40 bg-bad/10 px-4 py-2 text-sm font-medium text-bad transition hover:bg-bad/20 disabled:opacity-50"
                onClick={executeClearCorpus}
                disabled={clearLoading}
              >
                {clearLoading ? "Clearing…" : "Clear everything"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Full-viewport grid: chat | inspector */}
      <div
        className="grid w-full flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[minmax(0,1fr)_var(--inspector-width,clamp(360px,30vw,560px))]"
      >
        {/* Conversation column */}
        <section className="flex min-h-0 flex-col">
          <div
            ref={scrollRef}
            role="log"
            aria-live="polite"
            aria-label="Conversation"
            className="scroll-thin flex-1 overflow-y-auto px-3 py-4 md:px-6 xl:px-8"
          >
            <div className="mx-auto max-w-[var(--chat-max-width,900px)] space-y-4">
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
          <div className="mx-auto w-full max-w-[var(--chat-max-width,900px)] px-2 pb-2">
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
              ragStrategy={ragStrategy}
              onRagStrategyChange={setRagStrategy}
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
          {/* Always-visible Agent Activity Rail */}
          {traceAlwaysVisible && (
            <div className="border-b border-edge px-3 py-2">
              <AgentActivityRail
                activity={agentActivity}
                traceSteps={traceSteps}
                streaming={streaming}
              />
            </div>
          )}

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
                refreshKey={corpusRefreshKey}
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
        <div className="text-5xl" aria-hidden>
          🎙️
        </div>
        <h1 className="text-3xl font-bold tracking-tight text-fg">Talk to your data</h1>
        <p className="mx-auto max-w-lg text-base text-fg2">
          Grounded, cited answers from your indexed documents — by text or voice. Observable agentic
          RAG with full trace and evidence.
        </p>
      </div>
      <div className="flex w-full max-w-2xl flex-col gap-2">
        {suggestions.slice(0, 4).map((s) => (
          <button
            key={s}
            onClick={() => onAsk(s)}
            className="card card-hover px-4 py-3.5 text-left text-sm text-fg2"
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
