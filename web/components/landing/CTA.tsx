import Link from "next/link";

const REPO = "https://github.com/MHHamdan/Auralynq";

export function CTA() {
  return (
    <section className="relative mx-auto max-w-6xl px-4 py-20 md:px-6">
      <div className="glass relative overflow-hidden p-10 text-center md:p-16">
        <div className="orb left-1/2 top-0 h-64 w-64 -translate-x-1/2 bg-brand2/20" aria-hidden />
        <div className="relative">
          <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
            Ready to <span className="gradient-text">talk to your data?</span>
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-slate-300">
            Launch the app and ask your first question — no signup, no bill. It runs on your machine.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link href="/chat" className="btn-cta">
              Launch Auralynq →
            </Link>
            <a href={REPO} target="_blank" rel="noopener noreferrer" className="btn-outline">
              Read the docs
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
