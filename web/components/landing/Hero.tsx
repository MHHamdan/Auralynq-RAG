import Link from "next/link";
import { ChatPreview } from "@/components/landing/ChatPreview";

const REPO = "https://github.com/MHHamdan/Auralynq";

export function Hero() {
  return (
    <section className="relative overflow-hidden">
      {/* ambient gradient orbs + grid */}
      <div className="absolute inset-0 grid-bg" aria-hidden />
      <div className="orb left-[-6rem] top-[-4rem] h-72 w-72 bg-brand/20 animate-orb-drift" aria-hidden />
      <div
        className="orb right-[-5rem] top-10 h-80 w-80 bg-brand2/25 animate-orb-drift"
        style={{ animationDelay: "3s" }}
        aria-hidden
      />
      <div
        className="orb bottom-[-6rem] left-1/3 h-72 w-72 bg-accent/20 animate-orb-drift"
        style={{ animationDelay: "6s" }}
        aria-hidden
      />

      <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-4 py-20 md:px-6 md:py-28 lg:grid-cols-[1.05fr_0.95fr]">
        {/* copy */}
        <div className="reveal">
          <span className="chip mb-5">
            <span className="h-1.5 w-1.5 rounded-full bg-brand" />
            Local-first · $0 by default · Open source
          </span>
          <h1 className="text-4xl font-bold leading-[1.05] tracking-tight sm:text-5xl md:text-6xl">
            Talk to <span className="gradient-text">your data.</span>
          </h1>
          <p className="mt-5 max-w-xl text-lg leading-relaxed text-slate-300">
            Auralynq is an agentic, voice-enabled RAG platform with{" "}
            <span className="text-white">PathRAG graph retrieval</span>. Ask by text or voice and
            get grounded, cited answers — running entirely on your own machine, at zero cost by
            default.
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link href="/chat" className="btn-cta">
              Launch Auralynq →
            </Link>
            <a href={REPO} target="_blank" rel="noopener noreferrer" className="btn-outline">
              <span aria-hidden>★</span> View on GitHub
            </a>
          </div>

          <div className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-sm text-slate-300">
            <span>✓ No vendor lock-in</span>
            <span>✓ Citations on every claim</span>
            <span>✓ Voice in &amp; out</span>
          </div>
        </div>

        {/* product preview */}
        <div className="reveal flex justify-center lg:justify-end" style={{ animationDelay: "0.15s" }}>
          <div className="animate-float">
            <ChatPreview />
          </div>
        </div>
      </div>
    </section>
  );
}
