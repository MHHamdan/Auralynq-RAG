"use client";
import { Loader2, Search } from "lucide-react";

const ROUTE_LABEL: Record<string, string> = {
  fast: "fast retrieval",
  hybrid: "hybrid retrieval",
  graph: "graph traversal",
  relational: "graph traversal",
};

/**
 * "Assembling evidence" strip shown while an answer streams — surfaces the real
 * retrieval signals from the SSE `meta` event (route + detected entities) so the
 * wait shows work happening, not a bare spinner (Perplexity's finding: visible
 * progress makes users far more patient). Full progressive *source cards* would
 * need the backend to stream retrieved candidates in `meta`; this shows what the
 * pipeline actually reports today.
 */
export function StreamingEvidence({
  route,
  entities,
}: {
  route?: string;
  entities: string[];
}) {
  const label = route ? ROUTE_LABEL[route] ?? route.replace(/_/g, " ") : null;
  const shown = entities.slice(0, 6);
  return (
    <div className="mb-2 flex flex-wrap items-center gap-2 rounded-xl border border-edge bg-panel2/60 px-3 py-2 text-xs">
      <span className="inline-flex items-center gap-1.5 font-medium text-fg2">
        <Loader2 className="h-3.5 w-3.5 animate-spin text-brand" aria-hidden />
        Gathering evidence
      </span>
      {label && (
        <span className="inline-flex items-center gap-1 text-fg3">
          <Search className="h-3 w-3" aria-hidden />
          {label}
        </span>
      )}
      {shown.length > 0 && (
        <span className="flex flex-wrap items-center gap-1">
          {shown.map((e) => (
            <span
              key={e}
              className="rounded-full border border-edge bg-panel px-2 py-0.5 text-[11px] text-fg2 animate-pulse-soft"
            >
              {e}
            </span>
          ))}
        </span>
      )}
    </div>
  );
}
