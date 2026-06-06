"use client";
import type { Citation, CorpusSummary, InsufficientReason } from "@/lib/api";
import { Citations } from "@/components/Citations";
import { ConfidenceBar } from "@/components/ConfidenceBar";
import { Markdown } from "@/components/Markdown";
import { CopyButton } from "@/components/CopyButton";
import { InsufficientEvidence } from "@/components/InsufficientEvidence";
import { CorpusInventory } from "@/components/CorpusInventory";

export interface Turn {
  role: "user" | "assistant";
  text: string;
  citations?: Citation[];
  route?: string;
  rationale?: string;
  voice?: boolean;
  error?: boolean;
  status?: string;
  insufficient?: InsufficientReason | null;
  inventory?: CorpusSummary | null;
  question?: string;
  confidence?: number;
  semanticCoverage?: number;
}

function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1 py-2" aria-label="Assistant is typing">
      <span className="typing-dot" />
      <span className="typing-dot" style={{ animationDelay: "0.18s" }} />
      <span className="typing-dot" style={{ animationDelay: "0.36s" }} />
    </span>
  );
}

const ROUTE_META: Record<string, { label: string; color: string }> = {
  fast:   { label: "Fast retrieval",  color: "border-brand/40 text-brand" },
  hybrid: { label: "Hybrid retrieval", color: "border-accent/40 text-accent" },
  graph:  { label: "Graph traversal",  color: "border-brand2/40 text-brand2" },
};

function RouteTag({ route, rationale }: { route: string; rationale?: string }) {
  const meta = ROUTE_META[route] ?? { label: route, color: "border-edge text-fg3" };
  return (
    <div className="mb-2.5 flex flex-wrap items-center gap-2 border-b border-edge/50 pb-2.5">
      <span className={`tag font-medium ${meta.color}`}>{meta.label}</span>
      {rationale && <span className="text-xs text-fg3 truncate max-w-xs" title={rationale}>{rationale}</span>}
    </div>
  );
}

export function Message({
  turn,
  streaming,
  isLast,
  onRegenerate,
  onAsk,
  onIngest,
}: {
  turn: Turn;
  streaming: boolean;
  isLast: boolean;
  onRegenerate?: () => void;
  onAsk?: (q: string) => void;
  onIngest?: () => void;
}) {
  if (turn.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-brand2/20 px-4 py-2.5 leading-relaxed shadow-sm ring-1 ring-brand2/20">
          {turn.voice && <span className="mr-1.5 opacity-70">🎙</span>}
          {turn.text}
        </div>
      </div>
    );
  }

  // Corpus-inventory answer (what's in the collection) renders its own card.
  if (turn.inventory) {
    return (
      <div className="flex justify-start">
        <div className="w-full max-w-[94%] rounded-2xl rounded-bl-md border border-edge bg-panel2 px-4 py-4 shadow-md">
          <CorpusInventory summary={turn.inventory} question={turn.question} />
        </div>
      </div>
    );
  }

  const empty = !turn.text;
  const live = streaming && isLast;
  const hasCitations = (turn.citations?.length ?? 0) > 0;

  return (
    <div className="group flex justify-start">
      <div className="w-full max-w-[94%] rounded-2xl rounded-bl-md border border-edge bg-panel2 px-4 py-3.5 shadow-md">
        {turn.route && <RouteTag route={turn.route} rationale={turn.rationale} />}

        {empty && live ? (
          <TypingDots />
        ) : turn.error ? (
          <p className="whitespace-pre-wrap leading-relaxed text-bad">{turn.text}</p>
        ) : (
          <div className="prose-answer">
            <Markdown text={turn.text} streaming={live} />
            {live && <span className="ml-0.5 inline-block h-4 w-2 animate-pulse bg-brand/70 align-middle" />}
          </div>
        )}

        {turn.insufficient && (
          <InsufficientEvidence reason={turn.insufficient} onAsk={onAsk} onIngest={onIngest} />
        )}

        {hasCitations && <Citations citations={turn.citations!} />}

        {!streaming && !turn.error && turn.confidence != null && turn.confidence > 0 && (
          <ConfidenceBar
            data={{
              overall: turn.confidence,
              semanticCoverage: turn.semanticCoverage,
            }}
          />
        )}

        {!streaming && !empty && !turn.error && (
          <div className="mt-2.5 flex items-center gap-4 opacity-0 transition group-hover:opacity-100 focus-within:opacity-100">
            <CopyButton getText={() => turn.text} label="Copy" />
            {hasCitations && (
              <span className="text-xs text-fg3">{turn.citations!.length} source{turn.citations!.length === 1 ? "" : "s"}</span>
            )}
            {isLast && onRegenerate && (
              <button
                type="button"
                onClick={onRegenerate}
                aria-label="Regenerate answer"
                className="ml-auto inline-flex items-center gap-1 text-xs text-fg3 transition hover:text-brand"
              >
                ↻ Regenerate
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
