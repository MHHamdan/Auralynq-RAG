import type { ReactNode } from "react";

const POINTS: { title: string; body: string; icon: ReactNode }[] = [
  {
    title: "Local-first by default",
    body: "Runs entirely on your machine via rootless Podman. No account, no telemetry you didn't opt into, $0 to start. Your documents never leave the box.",
    icon: <path d="M4 10V7a8 8 0 0 1 16 0v3M5 10h14a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-6a2 2 0 0 1 2-2Z" />,
  },
  {
    title: "Honest abstention, not hallucination",
    body: "When the evidence doesn't support a reliable answer, Auralynq says so — and shows what it found and why it fell short — instead of inventing a confident lie.",
    icon: <path d="M12 3 2 21h20L12 3ZM12 9v5M12 17h.01" />,
  },
  {
    title: "Auralynq-RAG: observable agentic pipeline",
    body: "Auralynq-RAG is our own RAG strategy: calibrated confidence, intent routing, evidence sufficiency control, citation validation, and hallucination risk scoring — with a full trace for every query.",
    icon: <path d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2V9M9 21H5a2 2 0 0 1-2-2V9m0 0h18" />,
  },
  {
    title: "Choose your RAG algorithm",
    body: "Switch between 13+ strategies at runtime: Naive Vector, Hybrid, GraphRAG, PathRAG, and the full Auralynq-RAG pipeline — each with an availability status and latency estimate.",
    icon: <path d="M4 19V5M4 19h16M8 16v-5M12 16V8M16 16v-3" />,
  },
  {
    title: "Voice and text, one pipeline",
    body: "Spoken and typed questions flow through the same retrieval, grounding and citation path — so voice isn't a bolt-on demo, it's a first-class way to query your data.",
    icon: <path d="M9 3h6v8a3 3 0 0 1-6 0Z M5 11a7 7 0 0 0 14 0M12 18v3" />,
  },
  {
    title: "Research-ready open RAG lab",
    body: "Every query produces a structured trace log with retrieval metrics, citation coverage, and confidence scores — ready to export for RAGAS evaluation and strategy comparison.",
    icon: <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z" />,
  },
  {
    title: "Evidence & trace always visible",
    body: "A persistent Agent Activity rail shows live retrieval status, selected algorithm, coverage, confidence, and risk — no tab-clicking required.",
    icon: <path d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2V9M9 21H5a2 2 0 0 1-2-2V9m0 0h18" />,
  },
  {
    title: "Open-source & provider-agnostic",
    body: "MIT-spirited, inspectable, swappable. Start fully local, then bring your own Cohere / OpenAI / Anthropic keys to upgrade any single layer without lock-in.",
    icon: <path d="M12 2 4 6v6c0 5 3.5 8 8 10 4.5-2 8-5 8-10V6l-8-4Z M9 12l2 2 4-4" />,
  },
];

function Glyph({ children }: { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-5 w-5 text-brand"
      aria-hidden
    >
      {children}
    </svg>
  );
}

export function Differentiators() {
  return (
    <section id="why" className="relative mx-auto max-w-7xl px-4 py-14 md:px-6">
      <div className="mb-12 max-w-2xl">
        <p className="overline mb-2 text-accent">Why Auralynq</p>
        <h2 className="section-title">What makes Auralynq different?</h2>
        <p className="mt-3 text-lg text-fg2">
          Most RAG demos hide the seams. Auralynq makes trust, evidence and observability the
          product.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {POINTS.map((p) => (
          <div key={p.title} className="card card-hover flex gap-3 p-5">
            <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-edge bg-panel2">
              <Glyph>{p.icon}</Glyph>
            </span>
            <div>
              <h3 className="text-base font-semibold text-fg">{p.title}</h3>
              <p className="mt-1 text-sm leading-relaxed text-fg2">{p.body}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
