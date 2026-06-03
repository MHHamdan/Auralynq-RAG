import type { ReactNode } from "react";

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-6 w-6 text-brand"
      aria-hidden
    >
      {children}
    </svg>
  );
}

const FEATURES = [
  {
    title: "PathRAG graph retrieval",
    body: "Builds a knowledge graph from your corpus and traverses flow-pruned relational paths — so multi-hop questions get reasoned answers, not keyword soup.",
    icon: (
      <Icon>
        <circle cx="5" cy="6" r="2" />
        <circle cx="19" cy="6" r="2" />
        <circle cx="12" cy="18" r="2" />
        <path d="M7 6h10M6 8l5 8M18 8l-5 8" />
      </Icon>
    ),
  },
  {
    title: "Voice-native",
    body: "Speak your question and hear the answer back. Whisper ASR, speaker diarization and TTS are built in — with deterministic offline fallbacks.",
    icon: (
      <Icon>
        <rect x="9" y="3" width="6" height="11" rx="3" />
        <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
      </Icon>
    ),
  },
  {
    title: "Grounded & cited",
    body: "Every claim links back to its source — document, page, speaker and timestamp. No silent hallucinations; you can always check the receipts.",
    icon: (
      <Icon>
        <path d="M4 5a2 2 0 0 1 2-2h9l5 5v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z" />
        <path d="M14 3v5h5M8 13h8M8 17h5" />
      </Icon>
    ),
  },
  {
    title: "Hybrid retrieval",
    body: "Dense + sparse search fused with reciprocal-rank fusion, a cross-encoder reranker, MMR de-duplication and lost-in-the-middle reordering.",
    icon: (
      <Icon>
        <path d="M3 6h18M6 12h12M9 18h6" />
      </Icon>
    ),
  },
  {
    title: "Agentic & observable",
    body: "An adaptive router picks fast vector search or deep graph traversal, runs a self-checking loop, and shows you the full reasoning trace and evidence paths.",
    icon: (
      <Icon>
        <circle cx="12" cy="12" r="3" />
        <path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2" />
      </Icon>
    ),
  },
  {
    title: "Local-first & $0",
    body: "Runs entirely on your machine via rootless Podman — no account, no bill. Bring your own keys (Cohere, OpenAI, Anthropic) to upgrade any component.",
    icon: (
      <Icon>
        <rect x="3" y="4" width="18" height="12" rx="2" />
        <path d="M7 20h10M9 16v4M15 16v4" />
      </Icon>
    ),
  },
];

export function Features() {
  return (
    <section id="features" className="relative mx-auto max-w-6xl px-4 py-20 md:px-6">
      <div className="mb-12 max-w-2xl">
        <p className="mb-2 text-sm font-semibold uppercase tracking-widest text-brand">Capabilities</p>
        <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
          Everything a serious RAG stack needs — in one local binary
        </h2>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((f) => (
          <div key={f.title} className="glass glass-hover group p-6">
            <div className="mb-4 inline-flex rounded-xl border border-white/10 bg-white/5 p-2.5">
              {f.icon}
            </div>
            <h3 className="mb-2 text-lg font-semibold text-white">{f.title}</h3>
            <p className="text-sm leading-relaxed text-slate-300">{f.body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
