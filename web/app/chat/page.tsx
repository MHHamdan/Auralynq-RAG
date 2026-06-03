"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  AnswerResult,
  PathEvidence,
  StreamEvent,
  TraceSpan,
  askStream,
  health,
} from "@/lib/api";
import { Message, type Turn } from "@/components/Message";
import { TracePanel } from "@/components/TracePanel";
import { EvidencePaths } from "@/components/EvidencePaths";
import { IngestPanel } from "@/components/IngestPanel";
import { EvalPanel } from "@/components/EvalPanel";
import { VoiceRecorder } from "@/components/VoiceRecorder";

// Corpus-agnostic prompts so the suggestions stay useful whatever you've indexed.
const SUGGESTIONS = [
  "Summarize the key points of my documents.",
  "What topics do the indexed sources cover?",
  "List the main entities and how they relate.",
];
const STORE_KEY = "auralynq.chat.v1";

export default function Home() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [trace, setTrace] = useState<TraceSpan[]>([]);
  const [paths, setPaths] = useState<PathEvidence[]>([]);
  const [seeds, setSeeds] = useState<string[]>([]);
  const [tab, setTab] = useState<"trace" | "evidence" | "ingest" | "eval">("trace");
  const [showPanel, setShowPanel] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [providers, setProviders] = useState<{ subsystem: string; provider: string }[]>([]);

  const scrollRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // --- providers badge + restore persisted conversation -------------------
  useEffect(() => {
    health()
      .then((h) => setProviders(h.providers || []))
      .catch(() => {});
    try {
      const raw = localStorage.getItem(STORE_KEY);
      if (raw) setTurns(JSON.parse(raw));
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

  // Auto-grow the composer textarea.
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`;
  }, [input]);

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
    setPaths([]);
    setSeeds([]);
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      await askStream(
        q,
        (e: StreamEvent) => {
          if (e.type === "meta") {
            setPaths(e.path_evidence || []);
            setSeeds(e.seeds || []);
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
            patchLast({ text: e.answer, citations: e.citations });
          }
        },
        ac.signal,
      );
    } catch (err) {
      if (ac.signal.aborted) {
        setTurns((t) => {
          const c = [...t];
          const last = c[c.length - 1];
          if (last?.role === "assistant" && !last.text) c[c.length - 1] = { ...last, text: "⏹ Stopped." };
          return c;
        });
      } else {
        patchLast({ text: `Couldn't reach the backend: ${(err as Error).message}`, error: true });
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }, []);

  const send = useCallback(
    (q: string) => {
      if (!q.trim() || streaming) return;
      setInput("");
      setShowPanel(false);
      setTurns((t) => [...t, { role: "user", text: q }, { role: "assistant", text: "" }]);
      void runStream(q);
    },
    [streaming, runStream],
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
    try {
      localStorage.removeItem(STORE_KEY);
    } catch {
      /* ignore */
    }
    taRef.current?.focus();
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
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-7xl flex-col gap-4 p-4 md:p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link href="/" className="text-2xl font-bold tracking-tight" aria-label="Auralynq home">
            🎙️ <span className="text-brand">Aura</span>
            <span className="text-brand2">lynq</span>
          </Link>
          <p className="hidden text-sm text-slate-400 sm:block">
            Talk to Your Data — agentic voice RAG · PathRAG
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="hidden flex-wrap gap-1 md:flex">
            {providers.slice(0, 4).map((p) => (
              <span key={p.subsystem} className="tag" title={`${p.subsystem}: ${p.provider}`}>
                {p.subsystem}: <span className="text-brand">{p.provider}</span>
              </span>
            ))}
          </div>
          <button
            className="btn-ghost text-sm"
            onClick={newChat}
            aria-label="Start a new chat (Ctrl/Cmd+K)"
            title="New chat (⌘K)"
          >
            + New
          </button>
        </div>
      </header>

      <div className="grid flex-1 gap-4 lg:grid-cols-[1.4fr_1fr]">
        {/* Chat column */}
        <section className="card flex min-h-[62vh] flex-col">
          <div
            ref={scrollRef}
            role="log"
            aria-live="polite"
            aria-label="Conversation"
            className="scroll-thin flex-1 space-y-3 overflow-y-auto pr-1"
          >
            {turns.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
                <div className="space-y-1">
                  <p className="text-lg font-medium text-slate-200">Ask Auralynq anything</p>
                  <p className="text-sm text-slate-400">
                    Grounded, cited answers from your data — by text or voice.
                  </p>
                </div>
                <div className="flex flex-wrap justify-center gap-2">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} className="btn-ghost text-sm" onClick={() => send(s)}>
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              turns.map((t, i) => (
                <div key={i} className="msg-in">
                  <Message
                    turn={t}
                    streaming={streaming}
                    isLast={i === turns.length - 1}
                    onRegenerate={t.role === "assistant" ? regenerate : undefined}
                  />
                </div>
              ))
            )}
          </div>

          <div className="mt-3 space-y-2 border-t border-edge pt-3">
            <VoiceRecorder onResult={onVoice} />
            <form
              className="flex items-end gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                send(input);
              }}
            >
              <textarea
                ref={taRef}
                value={input}
                rows={1}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send(input);
                  }
                }}
                placeholder="Ask Auralynq…  (Enter to send · Shift+Enter for a new line)"
                aria-label="Ask a question"
                className="scroll-thin max-h-40 flex-1 resize-none rounded-xl border border-edge bg-ink/60 px-4 py-2 leading-relaxed outline-none transition focus:border-brand"
              />
              {streaming ? (
                <button type="button" onClick={stop} className="btn-ghost" aria-label="Stop generating (Esc)">
                  ◼ Stop
                </button>
              ) : (
                <button className="btn-brand" disabled={!input.trim()} aria-label="Send">
                  Ask
                </button>
              )}
            </form>
            <div className="flex items-center justify-between px-1 text-[11px] text-slate-400">
              <span>{turns.length > 0 ? `${Math.ceil(turns.length / 2)} message(s) · saved locally` : "Local-first · $0 default"}</span>
              <button className="hover:text-brand lg:hidden" onClick={() => setShowPanel((v) => !v)}>
                {showPanel ? "Hide details" : "Show details"}
              </button>
            </div>
          </div>
        </section>

        {/* Side panel */}
        <section className={`card flex-col ${showPanel ? "flex" : "hidden"} lg:flex`}>
          <div className="mb-3 flex gap-1 text-sm">
            {(["trace", "evidence", "ingest", "eval"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                aria-pressed={tab === t}
                className={`rounded-lg px-3 py-1 capitalize transition ${
                  tab === t ? "bg-brand text-ink" : "border border-edge hover:bg-edge/40"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
          <div className="scroll-thin max-h-[70vh] flex-1 overflow-y-auto">
            {tab === "trace" && <TracePanel trace={trace} />}
            {tab === "evidence" && <EvidencePaths paths={paths} seeds={seeds} />}
            {tab === "ingest" && <IngestPanel />}
            {tab === "eval" && <EvalPanel />}
          </div>
        </section>
      </div>

      <footer className="text-center text-xs text-slate-400">
        Auralynq · local-first · grounded answers with citations, spans &amp; timestamps
      </footer>

      {/* transient toast */}
      {toast && (
        <div
          role="status"
          className="fixed bottom-5 left-1/2 -translate-x-1/2 rounded-xl border border-edge bg-panel px-4 py-2 text-sm shadow-lg"
        >
          {toast}
        </div>
      )}
    </main>
  );
}
