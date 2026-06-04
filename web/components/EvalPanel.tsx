"use client";
import { useEffect, useState } from "react";
import { evalReport } from "@/lib/api";

const PLANNED = [
  { name: "Groundedness", body: "Is every claim supported by retrieved evidence?" },
  { name: "Citation coverage", body: "Share of statements that carry a citation." },
  { name: "Retrieval quality", body: "recall@k · nDCG@10 · MRR across retrievers." },
  { name: "Answer latency", body: "p50 / p95 end-to-end response time." },
  { name: "Abstention correctness", body: "Does it refuse exactly when evidence is insufficient?" },
];

const FEEDBACK_KEY = "auralynq.feedback.v1";
type Vote = "helpful" | "not-helpful" | "citation-ok" | "citation-wrong" | "unsupported";

const FEEDBACK: { id: Vote; label: string; good?: boolean }[] = [
  { id: "helpful", label: "👍 Helpful", good: true },
  { id: "not-helpful", label: "👎 Not helpful" },
  { id: "citation-ok", label: "✓ Citation correct", good: true },
  { id: "citation-wrong", label: "✕ Citation wrong" },
  { id: "unsupported", label: "⚠ Answer unsupported" },
];

export function EvalPanel() {
  const [report, setReport] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [flash, setFlash] = useState<string | null>(null);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(FEEDBACK_KEY);
      if (raw) setCounts(JSON.parse(raw));
    } catch {
      /* ignore */
    }
  }, []);

  async function load() {
    setLoading(true);
    try {
      setReport(await evalReport());
    } finally {
      setLoading(false);
    }
  }

  function vote(v: Vote) {
    setCounts((prev) => {
      const next = { ...prev, [v]: (prev[v] || 0) + 1 };
      try {
        localStorage.setItem(FEEDBACK_KEY, JSON.stringify(next));
      } catch {
        /* ignore quota */
      }
      return next;
    });
    setFlash("Thanks — feedback saved locally");
    setTimeout(() => setFlash(null), 1800);
  }

  const variants = report?.retrieval ? Object.entries(report.retrieval as Record<string, any>) : [];
  const hasReport = variants.length > 0;

  return (
    <div className="space-y-3">
      {/* manual feedback widget */}
      <section className="card-inset">
        <h3 className="mb-2 text-sm font-semibold text-fg">Rate the last answer</h3>
        <div className="flex flex-wrap gap-1.5">
          {FEEDBACK.map((f) => (
            <button
              key={f.id}
              onClick={() => vote(f.id)}
              className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
                f.good
                  ? "border-ok/40 text-ok hover:bg-ok/10"
                  : "border-edge text-fg2 hover:border-warn/50 hover:text-warn"
              }`}
            >
              {f.label}
              {counts[f.id] ? <span className="ml-1 opacity-70">· {counts[f.id]}</span> : null}
            </button>
          ))}
        </div>
        {flash && <p className="mt-2 text-[11px] text-ok">{flash}</p>}
      </section>

      {/* report (if available) */}
      <section className="card-inset">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-fg">Evaluation report</h3>
          <button className="btn-ghost px-2.5 py-1 text-xs" onClick={load} disabled={loading}>
            {loading ? "Loading…" : hasReport ? "Reload" : "Load report"}
          </button>
        </div>

        {hasReport ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-fg3">
                <tr>
                  <th className="text-left font-medium">retriever</th>
                  <th className="font-medium">recall@k</th>
                  <th className="font-medium">nDCG@10</th>
                  <th className="font-medium">MRR</th>
                  <th className="font-medium">p50 ms</th>
                </tr>
              </thead>
              <tbody>
                {variants.map(([name, m]) => (
                  <tr key={name} className="border-t border-edge">
                    <td className="py-1 text-fg">{name}</td>
                    <td className="text-center text-fg2">{m.recall_at_k}</td>
                    <td className="text-center text-fg2">{m.ndcg_at_10}</td>
                    <td className="text-center text-fg2">{m.mrr}</td>
                    <td className="text-center text-fg2">{m.latency_p50_ms}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {report?.agentic?.ragas && (
              <p className="mt-2 text-xs text-fg3">
                Ragas ({report.agentic.ragas.provider}): faithfulness{" "}
                {report.agentic.ragas.faithfulness} · relevancy {report.agentic.ragas.answer_relevancy}{" "}
                · ctx-precision {report.agentic.ragas.context_precision}
              </p>
            )}
          </div>
        ) : (
          <p className="text-sm text-fg3">
            No report yet — run <code className="text-brand">make eval</code> to generate retrieval &
            groundedness metrics.
          </p>
        )}
      </section>

      {/* planned evals */}
      <section className="card-inset">
        <h3 className="mb-2 text-sm font-semibold text-fg">Planned evaluations</h3>
        <ul className="space-y-1.5">
          {PLANNED.map((p) => (
            <li key={p.name} className="flex items-start gap-2 text-sm">
              <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-brand" aria-hidden />
              <span>
                <span className="font-medium text-fg">{p.name}</span>{" "}
                <span className="text-fg3">— {p.body}</span>
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
