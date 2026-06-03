import { Citation, PathEvidence } from "@/lib/api";

function CoverageMeter({ coverage }: { coverage: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, coverage)) * 100);
  const cls = pct >= 60 ? "bg-emerald-400" : pct >= 35 ? "bg-amber-400" : "bg-rose-400";
  return (
    <div className="rounded-xl border border-edge bg-ink/40 p-2.5">
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-300">Evidence coverage</span>
        <span className="font-semibold text-slate-100">{pct}%</span>
      </div>
      <div className="mt-1.5 h-2 w-full rounded-full bg-edge/50">
        <div className={`h-2 rounded-full ${cls}`} style={{ width: `${Math.max(pct, 2)}%` }} />
      </div>
      <p className="mt-1.5 text-[11px] text-slate-400">
        Share of the question&apos;s key terms covered by retrieved evidence.
      </p>
    </div>
  );
}

function Section({
  title,
  count,
  children,
  open = true,
}: {
  title: string;
  count?: number;
  children: React.ReactNode;
  open?: boolean;
}) {
  return (
    <details open={open} className="rounded-xl border border-edge bg-ink/30">
      <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-slate-200">
        {title}
        {typeof count === "number" && (
          <span className="ml-2 rounded-full bg-edge/60 px-2 py-0.5 text-xs text-slate-300">
            {count}
          </span>
        )}
      </summary>
      <div className="px-3 pb-3">{children}</div>
    </details>
  );
}

export function EvidencePaths({
  paths,
  seeds,
  coverage = 0,
  citations = [],
}: {
  paths: PathEvidence[];
  seeds: string[];
  coverage?: number;
  citations?: Citation[];
}) {
  const hasAnything = paths?.length || citations?.length || seeds?.length;
  if (!hasAnything)
    return (
      <p className="text-sm text-slate-500">
        Evidence appears here after a query — vector hits, PathRAG graph paths, and the citations
        the answer was grounded on.
      </p>
    );

  return (
    <div className="space-y-3">
      <CoverageMeter coverage={coverage} />

      {/* Final answer citations = the reranked vector evidence actually used. */}
      <Section title="Answer citations" count={citations.length} open={citations.length > 0}>
        {citations.length ? (
          <ol className="space-y-1.5">
            {citations.map((c) => (
              <li key={c.marker} className="flex items-start gap-2 text-sm">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand2/20 text-xs text-brand2">
                  {c.marker}
                </span>
                <span className="min-w-0">
                  <span className="text-slate-200">{c.source}</span>{" "}
                  <span className="text-slate-400">
                    {c.speaker ? `· ${c.speaker} ` : ""}
                    {c.locator}
                  </span>
                  <span className="ml-1 rounded bg-edge/50 px-1 text-[10px] text-slate-400">
                    {c.source_type}
                  </span>
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-xs text-slate-500">No citations attached to the answer.</p>
        )}
      </Section>

      {/* Graph evidence = PathRAG multi-hop paths. */}
      <Section title="Graph evidence (PathRAG)" count={paths?.length || 0} open={!!paths?.length}>
        {seeds?.length > 0 && (
          <div className="mb-2 flex flex-wrap items-center gap-1">
            <span className="text-xs text-slate-400">seeds:</span>
            {seeds.map((s) => (
              <span key={s} className="tag border-brand2/40 text-brand2">
                {s}
              </span>
            ))}
          </div>
        )}
        {paths?.length ? (
          <div className="space-y-2">
            {paths.map((p, i) => (
              <div key={i} className="rounded-xl border border-edge bg-ink/40 p-2">
                <div className="flex flex-wrap items-center gap-1 text-sm">
                  {p.nodes.map((n, j) => (
                    <span key={j} className="flex items-center gap-1">
                      <span className="rounded-md bg-edge/60 px-2 py-0.5">{n}</span>
                      {j < p.relations.length && (
                        <span className="text-xs text-brand">—{p.relations[j]}→</span>
                      )}
                    </span>
                  ))}
                </div>
                <div className="mt-1.5 flex items-center gap-2">
                  <div className="h-1.5 flex-1 rounded-full bg-edge/50">
                    <div
                      className="h-1.5 rounded-full bg-brand2"
                      style={{ width: `${Math.round(p.reliability * 100)}%` }}
                    />
                  </div>
                  <span className="text-xs text-slate-400">
                    reliability {p.reliability.toFixed(2)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-slate-500">
            No graph paths — this was answered by vector retrieval alone.
          </p>
        )}
      </Section>

      <p className="px-1 text-[11px] text-slate-500">
        Why this evidence: passages are ranked by hybrid (dense + sparse) retrieval, expanded along
        reliable graph relations, reranked, then only cited sources are kept.
      </p>
    </div>
  );
}
