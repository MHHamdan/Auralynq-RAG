// Static, stylized product mockup shown in the hero — "show the product".
export function ChatPreview() {
  return (
    <div className="glass relative w-full max-w-lg overflow-hidden p-4 sm:p-5">
      {/* window chrome */}
      <div className="mb-4 flex items-center gap-2">
        <span className="h-3 w-3 rounded-full bg-rose-400/70" />
        <span className="h-3 w-3 rounded-full bg-amber-400/70" />
        <span className="h-3 w-3 rounded-full bg-emerald-400/70" />
        <span className="ml-2 text-xs text-slate-400">auralynq · /chat</span>
        <span className="ml-auto chip !py-0.5 text-[10px]">
          <span className="h-1.5 w-1.5 rounded-full bg-brand animate-pulse-soft" /> live
        </span>
      </div>

      {/* user bubble */}
      <div className="mb-3 flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-md bg-brand2/20 px-4 py-2 text-sm ring-1 ring-brand2/20">
          How does PathRAG prune relational paths?
        </div>
      </div>

      {/* assistant answer */}
      <div className="rounded-2xl rounded-bl-md border border-edge bg-ink/60 px-4 py-3 text-sm">
        <div className="mb-2 flex items-center gap-2 text-[11px]">
          <span className="chip border-brand2/40 text-brand2">deep · graph</span>
          <span className="text-slate-500">relational query → graph traversal</span>
        </div>
        <p className="leading-relaxed text-slate-200">
          PathRAG scores candidate paths with a flow-based reliability metric, then prunes
          low-flow edges so only the most load-bearing relational chains reach the LLM
          <sup className="text-brand">[1]</sup>.
        </p>
        <div className="mt-3 flex flex-wrap gap-1.5 text-[10px] text-slate-400">
          <span className="chip">[1] pathrag.pdf · p.4</span>
          <span className="chip">Paris →[capital_of]→ France</span>
        </div>
      </div>

      {/* faux composer */}
      <div className="mt-4 flex items-center gap-2 rounded-xl border border-edge bg-ink/60 px-3 py-2 text-sm text-slate-500">
        <span className="flex-1">Ask Auralynq…</span>
        <span className="rounded-md bg-brand px-2 py-0.5 text-xs font-semibold text-ink">Ask</span>
      </div>
    </div>
  );
}
