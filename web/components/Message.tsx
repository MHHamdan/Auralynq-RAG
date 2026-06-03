"use client";
import type { Citation, InsufficientReason } from "@/lib/api";
import { Citations } from "@/components/Citations";
import { Markdown } from "@/components/Markdown";
import { CopyButton } from "@/components/CopyButton";
import { InsufficientEvidence } from "@/components/InsufficientEvidence";

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
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-brand2/20 px-4 py-2 leading-relaxed shadow-sm ring-1 ring-brand2/20">
          {turn.voice && <span className="mr-1 opacity-70">🎙</span>}
          {turn.text}
        </div>
      </div>
    );
  }

  const empty = !turn.text;
  const live = streaming && isLast;
  return (
    <div className="group flex justify-start">
      <div className="w-full max-w-[92%] rounded-2xl rounded-bl-md border border-edge bg-ink/50 px-4 py-3 shadow-sm">
        {turn.route && (
          <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
            <span
              className={`tag ${
                turn.route === "deep" ? "border-brand2/40 text-brand2" : "border-brand/40 text-brand"
              }`}
            >
              {turn.route === "deep" ? "deep · graph" : "fast"}
            </span>
            {turn.rationale && <span className="text-slate-400">{turn.rationale}</span>}
          </div>
        )}

        {empty && live ? (
          <TypingDots />
        ) : turn.error ? (
          <p className="whitespace-pre-wrap leading-relaxed text-rose-300">{turn.text}</p>
        ) : (
          <>
            <Markdown text={turn.text} streaming={live} />
            {live && <span className="ml-0.5 inline-block h-4 w-2 animate-pulse bg-brand/70 align-middle" />}
          </>
        )}

        {turn.insufficient && (
          <InsufficientEvidence reason={turn.insufficient} onAsk={onAsk} onIngest={onIngest} />
        )}

        {turn.citations && turn.citations.length > 0 && <Citations citations={turn.citations} />}

        {!streaming && !empty && !turn.error && (
          <div className="mt-2 flex items-center gap-4 opacity-0 transition group-hover:opacity-100 focus-within:opacity-100">
            <CopyButton getText={() => turn.text} label="Copy" />
            {isLast && onRegenerate && (
              <button
                type="button"
                onClick={onRegenerate}
                aria-label="Regenerate answer"
                className="inline-flex items-center gap-1 text-xs text-slate-400 transition hover:text-brand"
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
