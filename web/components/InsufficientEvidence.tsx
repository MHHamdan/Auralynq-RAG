"use client";
import type { InsufficientReason } from "@/lib/api";

/** Rich, trustworthy abstention card — explains *why* Auralynq refused and what
 * to do next, instead of a bare "Don't have enough evidence." */
export function InsufficientEvidence({
  reason,
  onAsk,
  onIngest,
}: {
  reason: InsufficientReason;
  onAsk?: (q: string) => void;
  onIngest?: () => void;
}) {
  return (
    <div className="mt-1 space-y-3 rounded-xl border border-amber-400/30 bg-amber-400/[0.06] p-3">
      <div className="flex items-start gap-2">
        <span aria-hidden className="text-lg leading-none">
          ⚖️
        </span>
        <div>
          <p className="font-medium text-slate-100">Not enough evidence to answer — honestly.</p>
          <p className="mt-0.5 text-sm text-slate-300">{reason.summary}</p>
        </div>
      </div>

      <div className="grid gap-2 text-xs sm:grid-cols-2">
        <div className="rounded-lg border border-edge bg-ink/40 p-2">
          <p className="text-slate-400">Detected entities</p>
          <div className="mt-1 flex flex-wrap gap-1">
            {reason.detected_entities.length ? (
              reason.detected_entities.map((e) => (
                <span key={e} className="tag border-brand2/40 text-brand2">
                  {e}
                </span>
              ))
            ) : (
              <span className="text-slate-500">none matched the corpus</span>
            )}
          </div>
        </div>
        <div className="rounded-lg border border-edge bg-ink/40 p-2">
          <p className="text-slate-400">Retrieval route attempted</p>
          <p className="mt-1 font-mono text-slate-200">{reason.route_attempted}</p>
        </div>
      </div>

      {reason.retrieved_snippets.length > 0 && (
        <details className="rounded-lg border border-edge bg-ink/40 p-2 text-sm">
          <summary className="cursor-pointer text-slate-300">
            Top retrieved snippets ({reason.retrieved_snippets.length}) — why they were insufficient
          </summary>
          <p className="mt-2 text-xs text-slate-400">{reason.why_insufficient}</p>
          <ul className="mt-2 space-y-2">
            {reason.retrieved_snippets.map((s, i) => (
              <li key={i} className="rounded-md border border-edge/70 bg-panel/40 p-2">
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span className="truncate">{s.source || "source"}</span>
                  <span>score {s.score.toFixed(3)}</span>
                </div>
                <p className="mt-1 text-xs text-slate-300">{s.text}…</p>
              </li>
            ))}
          </ul>
        </details>
      )}

      {!reason.retrieved_snippets.length && (
        <p className="text-xs text-slate-400">{reason.why_insufficient}</p>
      )}

      {reason.suggested_questions.length > 0 && (
        <div>
          <p className="text-xs text-slate-400">Try a question the corpus can actually support:</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {reason.suggested_questions.map((q) => (
              <button
                key={q}
                onClick={() => onAsk?.(q)}
                className="rounded-full border border-edge bg-panel/60 px-3 py-1 text-xs text-slate-200 transition hover:border-brand hover:text-brand"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {reason.suggest_ingest && (
        <button onClick={onIngest} className="btn-ghost text-sm">
          ＋ Ingest relevant documents
        </button>
      )}
    </div>
  );
}
