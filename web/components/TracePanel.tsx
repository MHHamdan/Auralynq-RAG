import { TraceSpan, TraceStep } from "@/lib/api";

const STATUS_META: Record<string, { icon: string; cls: string }> = {
  success: { icon: "✓", cls: "text-emerald-400" },
  warning: { icon: "!", cls: "text-amber-400" },
  failed: { icon: "✕", cls: "text-rose-400" },
  skipped: { icon: "–", cls: "text-slate-500" },
  running: { icon: "…", cls: "text-brand" },
  pending: { icon: "○", cls: "text-slate-500" },
};

const RISK_CLS: Record<string, string> = {
  none: "text-emerald-400",
  low: "text-emerald-400",
  medium: "text-amber-400",
  high: "text-rose-400",
};

export interface TraceMeta {
  route?: string;
  status?: string;
  confidence?: number;
  coverage?: number;
  elapsedMs?: number;
  phoenixUrl?: string | null;
}

function Stat({ label, value, cls }: { label: string; value: string; cls?: string }) {
  return (
    <div className="rounded-lg border border-edge bg-ink/40 px-2.5 py-1.5">
      <div className="text-[10px] uppercase tracking-wide text-slate-400">{label}</div>
      <div className={`text-sm font-semibold ${cls || "text-slate-100"}`}>{value}</div>
    </div>
  );
}

export function TracePanel({
  trace,
  steps,
  meta,
}: {
  trace: TraceSpan[];
  steps?: TraceStep[];
  meta?: TraceMeta;
}) {
  // Prefer structured steps; fall back to raw spans so old payloads still render.
  const rows: TraceStep[] =
    steps && steps.length
      ? steps
      : (trace || []).map((s, i) => ({
          id: i,
          name: s.name,
          label: s.name,
          status: "success" as const,
          duration_ms: s.duration_ms,
          provider: (s.attributes?.provider as string) || null,
          evidence_count: null,
          warnings: [],
          attributes: s.attributes || {},
        }));

  if (!rows.length)
    return (
      <p className="text-sm text-slate-500">
        Run a query to see the agent trajectory — every step with status, latency and provider.
      </p>
    );

  const max = Math.max(...rows.map((s) => s.duration_ms), 1);
  const total = rows.reduce((a, s) => a + s.duration_ms, 0);
  const bucket = (...keys: string[]) =>
    rows
      .filter((s) => keys.some((k) => s.name.toLowerCase().includes(k)))
      .reduce((a, s) => a + s.duration_ms, 0);
  const retrieval = bucket("retriev", "pathrag", "fus", "rerank");
  const generation = bucket("synthes");
  const abstained = meta?.status === "insufficient_evidence";
  const conf = meta?.confidence ?? 0;
  const cov = meta?.coverage ?? 0;
  const risk = abstained
    ? "none"
    : conf >= 0.6 && cov >= 0.6
      ? "low"
      : conf >= 0.4
        ? "medium"
        : "high";

  return (
    <div className="space-y-3">
      {/* summary dashboard */}
      <div className="grid grid-cols-3 gap-1.5">
        <Stat label="Total" value={`${(meta?.elapsedMs ?? total).toFixed(0)}ms`} />
        <Stat label="Retrieval" value={`${retrieval.toFixed(0)}ms`} />
        <Stat label="Generation" value={`${generation.toFixed(0)}ms`} />
        <Stat label="Coverage" value={`${Math.round(cov * 100)}%`} />
        <Stat label="Confidence" value={conf.toFixed(2)} />
        <Stat label="Hallu. risk" value={risk} cls={RISK_CLS[risk]} />
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="tag">route: {meta?.route || "—"}</span>
        <span className={`tag ${abstained ? "border-amber-400/40 text-amber-300" : ""}`}>
          {abstained ? "abstained" : "answered"}
        </span>
        {meta?.phoenixUrl && (
          <a
            href={meta.phoenixUrl}
            target="_blank"
            rel="noreferrer"
            className="tag border-accent/40 text-accent hover:bg-accent/10"
          >
            ↗ Open Phoenix trace
          </a>
        )}
      </div>

      {/* step waterfall */}
      <ol className="space-y-2">
        {rows.map((s) => {
          const sm = STATUS_META[s.status] || STATUS_META.success;
          return (
            <li key={s.id} className="text-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="flex min-w-0 items-center gap-2">
                  <span className={`font-mono ${sm.cls}`} aria-hidden>
                    {sm.icon}
                  </span>
                  <span className="truncate text-slate-200">{s.label}</span>
                </span>
                <span className="shrink-0 text-slate-400">{s.duration_ms.toFixed(1)}ms</span>
              </div>
              <div className="mt-1 h-1.5 w-full rounded-full bg-edge/50">
                <div
                  className={`h-1.5 rounded-full ${
                    s.status === "warning"
                      ? "bg-amber-400"
                      : s.status === "failed"
                        ? "bg-rose-400"
                        : "bg-brand"
                  }`}
                  style={{ width: `${Math.max((s.duration_ms / max) * 100, 3)}%` }}
                />
              </div>
              {(s.provider || (s.warnings && s.warnings.length > 0)) && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {s.provider && <span className="tag">provider: {s.provider}</span>}
                  {s.warnings?.map((w, j) => (
                    <span key={j} className="tag border-rose-400/40 text-rose-300">
                      {String(w).slice(0, 40)}
                    </span>
                  ))}
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
